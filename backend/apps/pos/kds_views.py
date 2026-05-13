import uuid

from django.db.models import Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import HasTenantContext

from .models import KdsLineStatus, Order, OrderLine, OrderStatus


class KdsTicketView(APIView):
    """Open orders with non-served lines for kitchen display."""

    permission_classes = [IsAuthenticated, HasTenantContext]

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

        line_qs = (
            OrderLine.objects.filter(is_voided=False)
            .exclude(kds_status=KdsLineStatus.SERVED)
            .select_related("menu_item")
        )
        if station:
            line_qs = line_qs.filter(kds_station=station)

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
        for o in orders:
            lines = [
                {
                    "line_id": str(ln.id),
                    "label": ln.label,
                    "quantity": str(ln.quantity),
                    "kds_station": ln.kds_station,
                    "kds_status": ln.kds_status,
                    "sort_order": ln.sort_order,
                }
                for ln in o.lines.all()
            ]
            if lines:
                out.append(
                    {
                        "order_id": str(o.id),
                        "bill_reference": o.bill_reference,
                        "table_label": o.table_label,
                        "lines": lines,
                    }
                )
        return Response({"outlet": str(oid), "orders": out})
