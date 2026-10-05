import uuid

from apps.access.outlets import membership_outlet_ids, outlet_belongs_to_membership
from apps.catalog.models import MenuItem
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import HasTenantContext, HasTenantModule, NotReadOnlyRole

from .models import StockBalance, StockCountSession, StockCountStatus, StockMovement
from .serializers import (
    StockBalanceSerializer,
    StockCountCompleteSerializer,
    StockCountSessionCreateSerializer,
    StockCountSessionSerializer,
    StockMovementSerializer,
    StockMovementWriteSerializer,
    StockTransferSerializer,
)
from .services import complete_stock_count_session


class StockBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule]
    required_staff_module = "inventory"
    serializer_class = StockBalanceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockBalance.objects.none()
        qs = (
            StockBalance.objects.filter(
                tenant=self.request.tenant,
                outlet_id__in=membership_outlet_ids(self.request.tenant_membership),
            )
            .select_related("outlet", "menu_item")
            .order_by("outlet", "menu_item__name")
        )
        outlet = self.request.query_params.get("outlet")
        if outlet:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet)))
            except ValueError:
                return StockBalance.objects.none()
        low = self.request.query_params.get("low_stock")
        if low and low.lower() in ("1", "true", "yes"):
            from django.db.models import F

            qs = qs.filter(
                menu_item__track_inventory=True,
                menu_item__reorder_level__isnull=False,
            ).filter(quantity__lte=F("menu_item__reorder_level"))
        return qs


class StockMovementViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "inventory"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockMovement.objects.none()
        qs = StockMovement.objects.filter(
            tenant=self.request.tenant,
            outlet_id__in=membership_outlet_ids(self.request.tenant_membership),
        ).select_related(
            "outlet", "menu_item", "order", "purchase_order", "created_by"
        )
        outlet = self.request.query_params.get("outlet")
        if outlet:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet)))
            except ValueError:
                return StockMovement.objects.none()
        tb = self.request.query_params.get("transfer_batch")
        if tb:
            try:
                qs = qs.filter(transfer_batch=uuid.UUID(str(tb)))
            except ValueError:
                return StockMovement.objects.none()
        po = self.request.query_params.get("purchase_order")
        if po:
            try:
                qs = qs.filter(purchase_order_id=uuid.UUID(str(po)))
            except ValueError:
                return StockMovement.objects.none()
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return StockMovementWriteSerializer
        return StockMovementSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement = serializer.save()
        return Response(
            StockMovementSerializer(movement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class StockTransferViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "inventory"
    serializer_class = StockTransferSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockMovement.objects.none()
        return StockMovement.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch, mov_out, mov_in = serializer.save()
        return Response(
            {
                "transfer_batch": str(batch),
                "from_movement_id": str(mov_out.id),
                "to_movement_id": str(mov_in.id),
            },
            status=status.HTTP_201_CREATED,
        )


class StockCountSessionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "inventory"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockCountSession.objects.none()
        qs = (
            StockCountSession.objects.filter(
                tenant=self.request.tenant,
                outlet_id__in=membership_outlet_ids(self.request.tenant_membership),
            )
            .select_related("outlet", "created_by")
            .prefetch_related("lines__menu_item")
        )
        outlet = self.request.query_params.get("outlet")
        if outlet:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet)))
            except ValueError:
                return StockCountSession.objects.none()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return StockCountSessionCreateSerializer
        return StockCountSessionSerializer

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        session = self.get_object()
        if not outlet_belongs_to_membership(request.tenant_membership, session.outlet_id):
            return Response(
                {"error": {"code": "forbidden", "message": "You cannot modify counts for this outlet."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if session.status != StockCountStatus.DRAFT:
            return Response(
                {"error": {"code": "invalid_state", "message": "Only draft sessions can be cancelled."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session.status = StockCountStatus.CANCELLED
        session.save(update_fields=["status", "updated_at"])
        return Response(StockCountSessionSerializer(session, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        session = self.get_object()
        if not outlet_belongs_to_membership(request.tenant_membership, session.outlet_id):
            return Response(
                {"error": {"code": "forbidden", "message": "You cannot modify counts for this outlet."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if session.status != StockCountStatus.DRAFT:
            return Response(
                {"error": {"code": "invalid_state", "message": "Only draft sessions can be completed."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = StockCountCompleteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tenant = request.tenant
        resolved = []
        for row in ser.validated_data["lines"]:
            mi = MenuItem.objects.filter(
                id=row["menu_item"],
                tenant_id=tenant.id,
                is_active=True,
            ).first()
            if mi is None:
                return Response(
                    {"lines": f"Unknown menu item: {row['menu_item']}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            resolved.append(
                {"menu_item": mi, "counted_quantity": row["counted_quantity"]},
            )
        complete_stock_count_session(
            session=session,
            resolved_lines=resolved,
            user=request.user,
            membership=request.tenant_membership,
        )
        session = (
            StockCountSession.objects.filter(pk=session.pk)
            .select_related("outlet", "created_by")
            .prefetch_related("lines__menu_item")
            .first()
        )
        return Response(
            StockCountSessionSerializer(session, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
