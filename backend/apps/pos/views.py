import uuid

from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import CanApproveRefunds, CanUseKds, HasTenantContext, HasTenantModule, NotReadOnlyRole
from apps.access.outlets import membership_outlet_ids
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
    RetailLineRefundSerializer,
    RetailLineReturnReadSerializer,
    TableSerializer,
)
from .services import (
    add_line_to_open_order,
    apply_promotion_to_order,
    charge_order_to_folio,
    create_order_with_lines,
    default_currency_for_tenant,
    record_order_payment,
    record_order_refund,
    refund_retail_line,
    resolve_folio_for_order,
    resolve_order_create,
    resolve_table,
    update_order_line_kds_status,
    void_open_order_line,
)


class TableViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"
    serializer_class = TableSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Table.objects.none()
        outlet_ids = membership_outlet_ids(self.request.tenant_membership)
        qs = Table.objects.filter(outlet__site__tenant=self.request.tenant, outlet_id__in=outlet_ids).select_related(
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
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        classes = list(self.permission_classes)
        if self.action in {"refunds", "retail_line_refunds"}:
            classes.append(CanApproveRefunds)
        if self.action == "kds_line":
            classes.append(CanUseKds)
        return [permission() for permission in classes]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        line_qs = OrderLine.objects.select_related("menu_item").order_by(
            "sort_order", "created_at"
        )
        outlet_ids = membership_outlet_ids(self.request.tenant_membership)
        qs = (
            Order.objects.filter(tenant=self.request.tenant, outlet_id__in=outlet_ids)
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

    @extend_schema(request=OrderPaySerializer, responses={200: PaymentSerializer, 201: PaymentSerializer},
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
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
            workstation_id=pay_ser.validated_data.get("workstation_id"),
            shift_id=pay_ser.validated_data.get("shift_id"),
        )
        order.refresh_from_db()
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="charge-to-folio")
    def charge_to_folio(self, request, pk=None):
        order = self.get_object()
        charge_order_to_folio(order=order, membership=request.tenant_membership, user=request.user)
        order.refresh_from_db()
        return Response(OrderReadSerializer(order, context=self.get_serializer_context()).data)

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
        from apps.accounts.models import MembershipRole

        role = request.tenant_membership.role
        bar_stations = {"bar", "drinks", "beverage", "bartender"}
        is_bar_line = (line.kds_station or "").strip().lower() in bar_stations
        if role == MembershipRole.BARTENDER and not is_bar_line:
            return Response({"error": {"code": "station_forbidden", "message": "Bar staff can only update drink prep tickets."}}, status=status.HTTP_403_FORBIDDEN)
        if role == MembershipRole.KITCHEN and is_bar_line:
            return Response({"error": {"code": "station_forbidden", "message": "Kitchen staff cannot update drink prep tickets."}}, status=status.HTTP_403_FORBIDDEN)
        update_order_line_kds_status(
            order=order,
            line=line,
            kds_status=ser.validated_data["kds_status"],
            kds_station=ser.validated_data.get("kds_station"),
            user=request.user,
        )
        order.refresh_from_db()
        return Response(OrderReadSerializer(order, context={"request": request}).data)

    @extend_schema(request=OrderRefundSerializer, responses={200: RefundSerializer, 201: RefundSerializer},
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
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
            workstation_id=ser.validated_data.get("workstation_id"),
            shift_id=ser.validated_data.get("shift_id"),
        )
        return Response(
            RefundSerializer(refund).data,
            status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
        )

    @extend_schema(request=RetailLineRefundSerializer, responses={200: RetailLineReturnReadSerializer, 201: RetailLineReturnReadSerializer},
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
    @action(detail=True, methods=["post"], url_path="retail-line-refunds")
    def retail_line_refunds(self, request, pk=None):
        order = self.get_object()
        idem, err = idempotency_header_or_error(request)
        if err:
            return err
        ser = RetailLineRefundSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        line = order.lines.filter(id=data["line_id"]).first()
        if line is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"line_id": "That line is not on this order."})
        ret, replay = refund_retail_line(
            order=order, line=line, quantity=data["quantity"], amount=data["amount"],
            reason=data.get("reason", ""), restock=data["restock"],
            payment_id=data.get("payment_id"), user=request.user, idempotency_key=idem,
            workstation_id=data.get("workstation_id"), shift_id=data.get("shift_id"),
        )
        return Response(RetailLineReturnReadSerializer(ret).data,
                        status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED)

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
