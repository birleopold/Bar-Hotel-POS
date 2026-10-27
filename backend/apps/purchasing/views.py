import uuid

from apps.access.outlets import membership_outlet_ids
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS
from rest_framework.response import Response

from apps.api.permissions import HasTenantContext, HasTenantModule, NotReadOnlyRole

from .models import PurchaseOrder, Supplier
from .serializers import (
    PurchaseOrderCreateSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderStatusUpdateSerializer,
    ConfirmMissingUnitCostSerializer,
    RecordSupplierPaymentSerializer,
    LinkSupplierPaymentInvoiceSerializer,
    RecordSupplierInvoiceSerializer,
    RecordSupplierReturnSerializer,
    SupplierInvoiceReadSerializer,
    ReceivePurchaseOrderSerializer,
    SupplierSerializer,
)
from .services import confirm_missing_unit_cost, receive_purchase_order_goods, record_supplier_payment, link_existing_supplier_payment_to_invoice, record_supplier_invoice, return_received_goods_to_supplier


class PurchasingActionPermission(BasePermission):
    """Match API writes to the existing staff purchasing capability policy."""
    message = "Your role cannot perform this purchasing action."

    def has_permission(self, request, view):
        from apps.staff.services.permissions import membership_has_purchasing_capability
        membership = getattr(request, "tenant_membership", None)
        if request.method in SAFE_METHODS:
            capability = "view"
        else:
            action = getattr(view, "action", None)
            capability = {
                "receive": "receive",
                "record_payment": "supplier_payment",
                "link_payment": "supplier_payment",
            }.get(action, "manage")
        return membership_has_purchasing_capability(membership, capability)


class SupplierViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole, PurchasingActionPermission]
    required_staff_module = "purchasing"
    serializer_class = SupplierSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Supplier.objects.none()
        return Supplier.objects.filter(tenant=self.request.tenant).order_by("name")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole, PurchasingActionPermission]
    required_staff_module = "purchasing"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PurchaseOrder.objects.none()
        oids = membership_outlet_ids(self.request.tenant_membership)
        qs = (
            PurchaseOrder.objects.filter(tenant=self.request.tenant, outlet_id__in=oids)
            .select_related("supplier", "outlet", "created_by", "reviewed_by")
            .prefetch_related("lines__menu_item", "receipts__lines__purchase_order_line__menu_item", "payments", "invoices__credits", "invoices__allocated_payments", "invoices__matched_lines")
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
        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "auto_approve": True},
        )
        serializer.is_valid(raise_exception=True)
        po = serializer.save()
        po = (
            PurchaseOrder.objects.filter(pk=po.pk)
            .select_related("supplier", "outlet", "created_by")
            .prefetch_related("lines__menu_item", "receipts__lines__purchase_order_line__menu_item", "payments")
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
            {key: value for key, value in x.items()
             if key in (
                 "line_id", "quantity", "cartons", "packages", "serial_numbers",
                 "batch_code", "expiry_date", "received_at",
             )}
            for x in ser.validated_data["lines"]
        ]
        receive_purchase_order_goods(
            po=po,
            lines_payload=lines_payload,
            user=request.user,
            membership=request.tenant_membership,
            discrepancy_note=ser.validated_data.get("discrepancy_note", ""),
            delivery_reference=ser.validated_data.get("delivery_reference", ""),
            note=ser.validated_data.get("note", ""),
            shipping_cost=ser.validated_data.get("shipping_cost", 0),
            duty_cost=ser.validated_data.get("duty_cost", 0),
            landed_cost_allocation=ser.validated_data.get(
                "landed_cost_allocation", "exclude"
            ),
        )
        po = (
            PurchaseOrder.objects.filter(pk=po.pk)
            .select_related("supplier", "outlet", "created_by")
            .prefetch_related("lines__menu_item", "receipts__lines__purchase_order_line__menu_item", "payments")
            .first()
        )
        return Response(PurchaseOrderSerializer(po, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="payments")
    def record_payment(self, request, pk=None):
        po = self.get_object()
        ser = RecordSupplierPaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payment, replay = record_supplier_payment(
            po=po, user=request.user, membership=request.tenant_membership,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **ser.validated_data,
        )
        from .serializers import SupplierPaymentSerializer
        return Response(SupplierPaymentSerializer(payment).data, status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="link-payment")
    def link_payment(self, request, pk=None):
        from rest_framework.exceptions import PermissionDenied
        from apps.staff.services.permissions import membership_has_purchasing_capability

        if not membership_has_purchasing_capability(request.tenant_membership, "supplier_payment"):
            raise PermissionDenied("Only an authorized purchasing manager can reconcile supplier payments.")
        po = self.get_object()
        ser = LinkSupplierPaymentInvoiceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payment, replay = link_existing_supplier_payment_to_invoice(
            po=po, user=request.user, membership=request.tenant_membership,
            **ser.validated_data,
        )
        from .serializers import SupplierPaymentSerializer
        return Response(SupplierPaymentSerializer(payment).data,
                        status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="invoices")
    def record_invoice(self, request, pk=None):
        po = self.get_object()
        serializer = RecordSupplierInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice, replay = record_supplier_invoice(
            po=po, user=request.user, membership=request.tenant_membership,
            **serializer.validated_data,
        )
        return Response(SupplierInvoiceReadSerializer(invoice).data,
                        status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="return-goods")
    def return_goods(self, request, pk=None):
        po = self.get_object()
        serializer = RecordSupplierReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result, replay = return_received_goods_to_supplier(
            po=po, user=request.user, membership=request.tenant_membership,
            **serializer.validated_data,
        )
        return Response({"id": str(result.pk), "quantity": str(result.quantity),
                         "reference": result.reference, "stock_movement_id": str(result.movement_id),
                         "credit_note_recorded": False},
                        status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="confirm-cost")
    def confirm_cost(self, request, pk=None):
        po = self.get_object()
        ser = ConfirmMissingUnitCostSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        confirm_missing_unit_cost(
            po=po, user=request.user, membership=request.tenant_membership, **ser.validated_data,
        )
        po = self.get_queryset().get(pk=po.pk)
        return Response(PurchaseOrderSerializer(po, context={"request": request}).data)
