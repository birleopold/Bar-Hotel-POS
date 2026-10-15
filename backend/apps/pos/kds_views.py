import uuid

from django.db.models import Prefetch
from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import ValidationError
from apps.accounts.models import MembershipRole
from apps.pos.services.kds import manage_kds_item, update_order_line_kds_status, kds_station_section
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.outlets import outlet_belongs_to_membership
from apps.api.permissions import CanUseKds, HasTenantContext, HasTenantModule

from .models import KdsLineStatus, Order, OrderLine, OrderStatus


class KdsTicketView(APIView):
    """Open orders with non-served lines for kitchen display."""

    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, CanUseKds]
    required_staff_module = "kitchen"

    @extend_schema(
        parameters=[
            OpenApiParameter("outlet", OpenApiTypes.UUID, required=True),
            OpenApiParameter("station", OpenApiTypes.STR, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        outlet = request.query_params.get("outlet")
        if not outlet:
            return Response(
                {"error": {"code": "outlet_required", "message": "Query parameter outlet is required."}},
                status=400,
            )
        try:
            oid = uuid.UUID(str(outlet))
        except ValueError:
            return Response(
                {"error": {"code": "invalid_outlet", "message": "outlet must be a UUID."}},
                status=400,
            )
        station = (request.query_params.get("station") or "").strip()
        if not outlet_belongs_to_membership(request.tenant_membership, oid):
            return Response({"error": {"code": "outlet_forbidden", "message": "You cannot use this prep queue."}}, status=403)

        line_qs = (
            OrderLine.objects.filter(is_voided=False)
            .exclude(kds_status=KdsLineStatus.SERVED)
            .select_related("menu_item")
        )
        if station:
            line_qs = line_qs.filter(kds_station=station)
        role = request.tenant_membership.role
        bar_stations = {"bar", "drinks", "beverage", "bartender"}
        if role == "bartender":
            line_qs = line_qs.filter(kds_station__iregex=r"^(bar|drinks|beverage|bartender)$")
        elif role == "kitchen":
            line_qs = line_qs.exclude(kds_station__iregex=r"^(bar|drinks|beverage|bartender)$")

        orders = (
            Order.objects.filter(
                tenant=request.tenant,
                outlet_id=oid,
                status=OrderStatus.OPEN,
            )
            .select_related("outlet", "table")
            .prefetch_related(Prefetch("lines", queryset=line_qs.order_by("sort_order", "created_at")))
            .order_by("created_at")
        )

        out = []
        now = timezone.now()
        overdue_minutes = 15
        for o in orders:
            lines = []
            for ln in o.lines.all():
                waiting = max(0, int((now - ln.created_at).total_seconds() // 60))
                lines.append({
                    "line_id": str(ln.id), "label": ln.label,
                    "quantity": str(ln.quantity), "kds_station": ln.kds_station,
                    "kds_status": ln.kds_status, "sort_order": ln.sort_order,
                    "is_rush": ln.kds_rush,
                    "modifiers": ln.modifiers_snapshot,
                    "waiting_minutes": waiting,
                    "overdue": waiting >= overdue_minutes and ln.kds_status not in (
                        KdsLineStatus.READY, KdsLineStatus.SERVED,
                    ),
                    "status_changed_at": (
                        ln.kds_status_changed_at.isoformat() if ln.kds_status_changed_at else None
                    ),
                })
            if lines:
                lines.sort(key=lambda row: (not row["is_rush"], -row["waiting_minutes"]))
                out.append({
                    "order_id": str(o.id), "bill_reference": o.bill_reference,
                    "table_label": o.table_label, "rush": any(row["is_rush"] for row in lines),
                    "oldest_wait_minutes": max(row["waiting_minutes"] for row in lines),
                    "lines": lines,
                })
        out.sort(key=lambda row: (not row["rush"], -row["oldest_wait_minutes"]))
        return Response({
            "outlet": str(oid), "orders": out,
            "overdue_after_minutes": overdue_minutes,
            "counts": {
                "tickets": len(out), "items": sum(len(row["lines"]) for row in out),
                "overdue": sum(int(line["overdue"]) for row in out for line in row["lines"]),
                "rush": sum(int(line["is_rush"]) for row in out for line in row["lines"]),
            },
        })

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        """Update one line only for a permitted outlet/station and role."""
        try:
            outlet_id = uuid.UUID(str(request.data.get("outlet") or ""))
            order_id = uuid.UUID(str(request.data.get("order_id") or ""))
            line_id = uuid.UUID(str(request.data.get("line_id") or ""))
        except ValueError:
            return Response({"error": {"code": "invalid_id", "message": "Choose valid IDs."}}, status=400)
        membership = request.tenant_membership
        if not membership.is_active or not outlet_belongs_to_membership(membership, outlet_id):
            return Response({"error": {"code": "outlet_forbidden", "message": "No access to this section."}}, status=403)
        order = Order.objects.filter(
            id=order_id, tenant=request.tenant, outlet_id=outlet_id,
            status=OrderStatus.OPEN,
        ).first()
        line = OrderLine.objects.filter(order=order, id=line_id, is_voided=False).first() if order else None
        if not line:
            return Response({"error": {"code": "not_found", "message": "Prep item not found."}}, status=404)
        section = kds_station_section(line.kds_station)
        if (membership.role == MembershipRole.KITCHEN and section == "bar") or (
                membership.role == MembershipRole.BARTENDER and section != "bar"):
            return Response({"error": {"code": "station_forbidden", "message": "Item belongs to another station."}}, status=403)
        action = str(request.data.get("action") or "").strip()
        try:
            if action in {"rush", "normal", "recall"}:
                updated, _changed = manage_kds_item(
                    order=order, line=line, membership=membership,
                    user=request.user, action=action,
                    reason=request.data.get("reason", ""),
                )
            elif action == "status":
                next_status = str(request.data.get("kds_status") or "").strip()
                updated = update_order_line_kds_status(
                    order=order, line=line, user=request.user,
                    kds_status=next_status, kds_station=None,
                )
            else:
                return Response({"error": {"code": "invalid_action", "message": "Choose a valid action."}}, status=400)
        except ValidationError as exc:
            return Response({"error": {"code": "invalid_transition", "message": exc.detail}}, status=400)
        return Response({
            "line_id": str(updated.id), "status": updated.kds_status,
            "is_rush": updated.kds_rush,
        })
