import uuid

from apps.access.outlets import membership_outlet_ids
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import HasTenantContext, NotReadOnlyRole

from .models import PurchaseOrder, Supplier
from .serializers import (
    PurchaseOrderCreateSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderStatusUpdateSerializer,
    ReceivePurchaseOrderSerializer,
    SupplierSerializer,
)
from .services import receive_purchase_order_goods


class SupplierViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = SupplierSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Supplier.objects.none()
        return Supplier.objects.filter(tenant=self.request.tenant).order_by("name")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PurchaseOrder.objects.none()
        oids = membership_outlet_ids(self.request.tenant_membership)
        qs = (
            PurchaseOrder.objects.filter(tenant=self.request.tenant, outlet_id__in=oids)
            .select_related("supplier", "outlet", "created_by")
            .prefetch_related("lines__menu_item", "receipts__lines__purchase_order_line__menu_item")
            .order_by("-created_at")
        )
        supplier = self.request.query_params.get("supplier")
        if supplier:
            try:
                qs = qs.filter(supplier_id=uuid.UUID(str(supplier)))
            except ValueError:
                return PurchaseOrder.objects.none()
        outlet = self.request.query_params.get("outlet")
        if outlet:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet)))
            except ValueError:
                return PurchaseOrder.objects.none()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st.strip())
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return PurchaseOrderCreateSerializer
        if self.action in ("partial_update", "update"):
            return PurchaseOrderStatusUpdateSerializer
        return PurchaseOrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        po = serializer.save()
        po = (
            PurchaseOrder.objects.filter(pk=po.pk)
            .select_related("supplier", "outlet", "created_by")
            .prefetch_related("lines__menu_item", "receipts__lines__purchase_order_line__menu_item")
            .first()
        )
        return Response(
            PurchaseOrderSerializer(po, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        po = self.get_object()
        ser = ReceivePurchaseOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        lines_payload = [
            {"line_id": x["line_id"], "quantity": x["quantity"]}
            for x in ser.validated_data["lines"]
        ]
        receive_purchase_order_goods(
            po=po,
            lines_payload=lines_payload,
            user=request.user,
            membership=request.tenant_membership,
            delivery_reference=ser.validated_data.get("delivery_reference", ""),
            note=ser.validated_data.get("note", ""),
        )
        po = (
            PurchaseOrder.objects.filter(pk=po.pk)
            .select_related("supplier", "outlet", "created_by")
            .prefetch_related("lines__menu_item", "receipts__lines__purchase_order_line__menu_item")
            .first()
        )
        return Response(PurchaseOrderSerializer(po, context={"request": request}).data)
