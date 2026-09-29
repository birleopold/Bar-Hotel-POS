import uuid

from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import CanApproveRefunds, HasTenantContext, NotReadOnlyRole
from apps.audit.services import log_audit
from .models import Order, OrderLine, Table
from .view_helpers import (
    idempotency_header_or_error,
    menu_item_for_order_or_error,
    order_line_or_error,
    promotion_for_order_or_error,
)
from .serializers import (
    OrderAddLineSerializer,
    OrderApplyPromotionSerializer,
    OrderCreateSerializer,
    OrderLineKdsSerializer,
    OrderLineReadSerializer,
    OrderListSerializer,
    OrderPaySerializer,
    OrderReadSerializer,
    OrderRefundSerializer,
    OrderUpdateSerializer,
    OrderVoidLineSerializer,
    PaymentSerializer,
    RefundSerializer,
    TableSerializer,
)
from .services import (
    add_line_to_open_order,
    apply_promotion_to_order,
    create_order_with_lines,
    default_currency_for_tenant,
    record_order_payment,
    record_order_refund,
    resolve_folio_for_order,
    resolve_order_create,
    resolve_table,
    update_order_line_kds_status,
    void_open_order_line,
)


class TableViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = TableSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Table.objects.none()
        qs = Table.objects.filter(outlet__site__tenant=self.request.tenant).select_related(
            "outlet", "outlet__site"
        )
        outlet = self.request.query_params.get("outlet")
        if outlet:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet)))
            except ValueError:
                return Table.objects.none()
        return qs.order_by("outlet", "sort_order", "label")


class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        classes = list(self.permission_classes)
        if self.action == "refunds":
            classes.append(CanApproveRefunds)
        return [permission() for permission in classes]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        line_qs = OrderLine.objects.select_related("menu_item").order_by(
            "sort_order", "created_at"
        )
        qs = (
            Order.objects.filter(tenant=self.request.tenant)
            .select_related("outlet", "table")
            .prefetch_related(Prefetch("lines", queryset=line_qs), "payments")
            .order_by("-created_at")
        )
        outlet_param = self.request.query_params.get("outlet")
        if outlet_param:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet_param)))
            except ValueError:
                return Order.objects.none()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return OrderListSerializer
        return OrderReadSerializer

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        ser = OrderUpdateSerializer(
            instance,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        instance.refresh_from_db()
        log_audit(
            tenant_id=request.tenant.id,
            user_id=request.user.id,
            action="order.updated",
            entity_type="order",
            entity_id=str(instance.id),
            payload=dict(ser.validated_data),
        )
        return Response(
            OrderReadSerializer(instance, context=self.get_serializer_context()).data
        )

    @action(detail=True, methods=["post"], url_path="payments")
    def payments(self, request, pk=None):
        order = self.get_object()
        idem, err = idempotency_header_or_error(request)
        if err:
            return err
        pay_ser = OrderPaySerializer(data=request.data)
        pay_ser.is_valid(raise_exception=True)
        payment, replay = record_order_payment(
            order=order,
            user=request.user,
            amount=pay_ser.validated_data["amount"],
            method=pay_ser.validated_data["method"],
            idempotency_key=idem,
        )
        order.refresh_from_db()
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="lines")
    def add_line(self, request, pk=None):
        order = self.get_object()
        ser = OrderAddLineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        item, err = menu_item_for_order_or_error(
            tenant_id=request.tenant.id,
            order=order,
            menu_item_id=ser.validated_data["menu_item"],
        )
        if err:
            return err
        line = add_line_to_open_order(
            order=order,
            menu_item=item,
            quantity=ser.validated_data["quantity"],
            user=request.user,
            modifier_option_ids=ser.validated_data.get("modifier_option_ids") or [],
        )
        order.refresh_from_db()
        return Response(
            OrderLineReadSerializer(line, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="void-line")
    def void_line(self, request, pk=None):
        order = self.get_object()
        ser = OrderVoidLineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        line, err = order_line_or_error(order, ser.validated_data["line_id"])
        if err:
            return err
        void_open_order_line(
            order=order,
            line=line,
            reason=ser.validated_data.get("reason") or "",
            user=request.user,
        )
        order.refresh_from_db()
        return Response(OrderReadSerializer(order, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="apply-promotion")
    def apply_promotion(self, request, pk=None):
        order = self.get_object()
        ser = OrderApplyPromotionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        promo, err = promotion_for_order_or_error(
            tenant_id=request.tenant.id,
            promotion_id=ser.validated_data["promotion_id"],
        )
        if err:
            return err
        apply_promotion_to_order(order=order, promotion=promo, user=request.user)
        order.refresh_from_db()
        return Response(OrderReadSerializer(order, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="kds-line")
    def kds_line(self, request, pk=None):
        order = self.get_object()
        ser = OrderLineKdsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        line, err = order_line_or_error(order, ser.validated_data["line_id"])
        if err:
            return err
        update_order_line_kds_status(
            order=order,
            line=line,
            kds_status=ser.validated_data["kds_status"],
            kds_station=ser.validated_data.get("kds_station"),
            user=request.user,
        )
        order.refresh_from_db()
        return Response(OrderReadSerializer(order, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="refunds")
    def refunds(self, request, pk=None):
        order = self.get_object()
        idem, err = idempotency_header_or_error(request)
        if err:
            return err
        ser = OrderRefundSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        refund, replay = record_order_refund(
            order=order,
            user=request.user,
            amount=ser.validated_data["amount"],
            reason=ser.validated_data.get("reason") or "",
            idempotency_key=idem,
            restock=ser.validated_data.get("restock") or False,
            payment_id=ser.validated_data.get("payment_id"),
        )
        return Response(
            RefundSerializer(refund).data,
            status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
        )

    def create(self, request, *args, **kwargs):
        ser = OrderCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        outlet, resolved_lines = resolve_order_create(
            request.tenant,
            request.tenant_membership,
            outlet_id=vd["outlet"],
            lines=vd["lines"],
        )
        folio = resolve_folio_for_order(
            request.tenant.id,
            request.tenant_membership,
            outlet,
            vd.get("folio"),
        )
        table = resolve_table(request.tenant.id, outlet.id, vd.get("table"))
        label = vd.get("table_label") or ""
        if table and not label.strip():
            label = table.label
        currency = default_currency_for_tenant(request.tenant)
        order = create_order_with_lines(
            tenant_id=request.tenant.id,
            outlet=outlet,
            created_by=request.user,
            currency=currency,
            table_label=label,
            lines=resolved_lines,
            table=table,
            folio=folio,
        )
        return Response(
            OrderReadSerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
