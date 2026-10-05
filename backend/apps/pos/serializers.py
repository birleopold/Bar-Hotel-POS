from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import MembershipRole
from apps.lodging.models import Folio, FolioStatus
from apps.tenants.models import Outlet

from .models import (
    KdsLineStatus,
    OfflineQueuedOperation,
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    PaymentMethod,
    Refund,
    Table,
)


class OrderLineInputSerializer(serializers.Serializer):
    menu_item = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    modifier_option_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )


class OrderCreateSerializer(serializers.Serializer):
    outlet = serializers.UUIDField()
    table = serializers.UUIDField(required=False, allow_null=True)
    table_label = serializers.CharField(required=False, allow_blank=True, default="")
    folio = serializers.UUIDField(required=False, allow_null=True)
    lines = OrderLineInputSerializer(many=True)

    def validate_lines(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value


class OrderLineReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLine
        fields = [
            "id",
            "menu_item",
            "label",
            "quantity",
            "unit_price",
            "line_total",
            "tax_amount",
            "sort_order",
            "is_voided",
            "void_reason",
            "voided_at",
            "kds_station",
            "kds_status",
            "modifiers_snapshot",
            "created_at",
        ]
        read_only_fields = (
            "id",
            "menu_item",
            "label",
            "quantity",
            "unit_price",
            "line_total",
            "tax_amount",
            "sort_order",
            "is_voided",
            "void_reason",
            "voided_at",
            "kds_station",
            "kds_status",
            "modifiers_snapshot",
            "created_at",
        )


class PaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source="order.id", read_only=True)

    shift_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "order_id",
            "shift_id",
            "amount",
            "method",
            "created_at",
        ]
        read_only_fields = (
            "id",
            "order_id",
            "shift_id",
            "amount",
            "method",
            "created_at",
        )


class OrderReadSerializer(serializers.ModelSerializer):
    lines = OrderLineReadSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    outlet_id = serializers.UUIDField(source="outlet.id", read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)
    table_id = serializers.UUIDField(source="table.id", read_only=True, allow_null=True)
    amount_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "bill_reference",
            "status",
            "table_id",
            "table_label",
            "outlet_id",
            "outlet_name",
            "currency",
            "subtotal",
            "tax_total",
            "discount_amount",
            "total",
            "amount_paid",
            "balance_due",
            "is_paid",
            "folio",
            "applied_promotion",
            "created_at",
            "updated_at",
            "lines",
            "payments",
        ]
        read_only_fields = (
            "id",
            "bill_reference",
            "status",
            "table_id",
            "table_label",
            "outlet_id",
            "outlet_name",
            "currency",
            "subtotal",
            "tax_total",
            "discount_amount",
            "total",
            "amount_paid",
            "balance_due",
            "is_paid",
            "folio",
            "applied_promotion",
            "created_at",
            "updated_at",
            "lines",
            "payments",
        )

    def get_amount_paid(self, obj: Order) -> str:
        from django.db.models import Sum

        s = obj.payments.aggregate(x=Sum("amount"))["x"] or Decimal("0")
        return str(s.quantize(Decimal("0.01")))

    def get_balance_due(self, obj: Order) -> str:
        from django.db.models import Sum

        paid = obj.payments.aggregate(x=Sum("amount"))["x"] or Decimal("0")
        bal = (obj.total - paid).quantize(Decimal("0.01"))
        return str(max(Decimal("0"), bal))


class OrderListSerializer(serializers.ModelSerializer):
    outlet_id = serializers.UUIDField(source="outlet.id", read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)
    table_id = serializers.UUIDField(source="table.id", read_only=True, allow_null=True)
    amount_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "bill_reference",
            "status",
            "table_id",
            "table_label",
            "outlet_id",
            "outlet_name",
            "discount_amount",
            "total",
            "amount_paid",
            "balance_due",
            "is_paid",
            "folio",
            "created_at",
        ]
        read_only_fields = (
            "id",
            "bill_reference",
            "status",
            "table_id",
            "table_label",
            "outlet_id",
            "outlet_name",
            "discount_amount",
            "total",
            "amount_paid",
            "balance_due",
            "is_paid",
            "folio",
            "created_at",
        )

    def get_amount_paid(self, obj: Order) -> str:
        from django.db.models import Sum

        s = obj.payments.aggregate(x=Sum("amount"))["x"] or Decimal("0")
        return str(s.quantize(Decimal("0.01")))

    def get_balance_due(self, obj: Order) -> str:
        from django.db.models import Sum

        paid = obj.payments.aggregate(x=Sum("amount"))["x"] or Decimal("0")
        bal = (obj.total - paid).quantize(Decimal("0.01"))
        return str(max(Decimal("0"), bal))


class OrderUpdateSerializer(serializers.ModelSerializer):
    folio = serializers.PrimaryKeyRelatedField(
        queryset=Folio.objects.none(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Order
        fields = ["status", "is_paid", "discount_amount", "folio"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["folio"].queryset = Folio.objects.filter(
                tenant=tenant, status=FolioStatus.OPEN
            )

    def validate(self, attrs: dict) -> dict:
        inst = self.instance
        if inst is None:
            return attrs
        if inst.status == OrderStatus.CANCELLED:
            raise serializers.ValidationError("Cancelled orders cannot be changed.")
        if inst.status == OrderStatus.CLOSED:
            raise serializers.ValidationError("Closed orders cannot be changed.")
        new_status = attrs.get("status", inst.status)
        if new_status not in (OrderStatus.OPEN, OrderStatus.CANCELLED, OrderStatus.CLOSED):
            raise serializers.ValidationError({"status": "Invalid status."})
        if new_status == OrderStatus.CLOSED:
            raise serializers.ValidationError({"status": "Close by recording payment or charging the balance to a folio."})
        if "is_paid" in attrs:
            raise serializers.ValidationError({"is_paid": "Payment state is set by the settlement workflow."})
        if new_status == OrderStatus.CANCELLED and inst.payments.exists():
            raise serializers.ValidationError({"status": "Refund recorded payments before cancelling this order."})

        if "discount_amount" in attrs or "folio" in attrs:
            if inst.status != OrderStatus.OPEN or inst.is_paid:
                raise serializers.ValidationError(
                    "Discount and folio can only be changed on open, unpaid orders."
                )

        folio = attrs.get("folio", serializers.empty)
        if folio is not serializers.empty and folio is not None:
            if folio.site_id != inst.outlet.site_id:
                raise serializers.ValidationError(
                    {"folio": "Folio must belong to the same site as the order outlet."}
                )
            m = self.context["request"].tenant_membership
            if (m.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or m.sites.exists()) and folio.site_id not in m.sites.values_list("pk", flat=True):
                raise serializers.ValidationError({"folio": "You cannot attach this folio."})

        if "discount_amount" in attrs:
            da = attrs["discount_amount"]
            if da < 0:
                raise serializers.ValidationError({"discount_amount": "Must be non-negative."})
            from django.db.models import Sum

            paid = (
                Payment.objects.filter(order_id=inst.id).aggregate(s=Sum("amount"))["s"]
                or Decimal("0")
            )
            if paid > 0:
                raise serializers.ValidationError(
                    {"discount_amount": "Cannot change discount after partial payments exist."}
                )

        return attrs

    def update(self, instance: Order, validated_data: dict) -> Order:
        from .services import recalculate_order_totals

        inst = super().update(instance, validated_data)
        if "discount_amount" in validated_data:
            recalculate_order_totals(inst)
            inst.refresh_from_db()
        return inst


class OrderPaySerializer(serializers.Serializer):
    workstation_id = serializers.UUIDField(required=False, allow_null=True)
    shift_id = serializers.UUIDField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=PaymentMethod.choices)


class OrderAddLineSerializer(serializers.Serializer):
    menu_item = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    modifier_option_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )


class OrderVoidLineSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class OrderRefundSerializer(serializers.Serializer):
    workstation_id = serializers.UUIDField(required=False, allow_null=True)
    shift_id = serializers.UUIDField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    restock = serializers.BooleanField(default=False)
    payment_id = serializers.UUIDField(required=False, allow_null=True)


class RetailLineRefundSerializer(serializers.Serializer):
    workstation_id = serializers.UUIDField(required=False, allow_null=True)
    shift_id = serializers.UUIDField(required=False, allow_null=True)
    line_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal("0.001"))
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    restock = serializers.BooleanField(default=False)
    payment_id = serializers.UUIDField(required=False, allow_null=True)


class RefundSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source="order.id", read_only=True)

    shift_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Refund
        fields = [
            "id",
            "order_id",
            "shift_id",
            "payment",
            "amount",
            "reason",
            "restocked",
            "created_at",
        ]
        read_only_fields = (
            "id",
            "order_id",
            "shift_id",
            "payment",
            "amount",
            "reason",
            "restocked",
            "created_at",
        )


class RetailLineReturnReadSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    order_line_id = serializers.UUIDField(read_only=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, read_only=True)
    reason = serializers.CharField(read_only=True)
    restocked = serializers.BooleanField(read_only=True)
    refund = RefundSerializer(read_only=True)


class TableSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)

    class Meta:
        model = Table
        fields = [
            "id",
            "outlet",
            "outlet_name",
            "label",
            "capacity",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "outlet_name", "created_at", "updated_at")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["outlet"].queryset = Outlet.objects.filter(
                site__tenant=tenant, is_active=True
            ).select_related("site")

    def validate_outlet(self, value: Outlet) -> Outlet:
        if value.site.tenant_id != self.context["request"].tenant.id:
            raise serializers.ValidationError("Outlet must belong to the current tenant.")
        return value


class OrderApplyPromotionSerializer(serializers.Serializer):
    promotion_id = serializers.UUIDField()


class OrderLineKdsSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    kds_status = serializers.ChoiceField(choices=KdsLineStatus.choices)
    kds_station = serializers.CharField(required=False, allow_blank=True, max_length=32)


class OfflineOrderCreatePayloadSerializer(serializers.Serializer):
    """Payload for ``operation_type`` = ``order_create`` on offline sync."""

    lines = OrderLineInputSerializer(many=True)
    table = serializers.UUIDField(required=False, allow_null=True)
    table_label = serializers.CharField(required=False, allow_blank=True, default="", max_length=64)
    folio = serializers.UUIDField(required=False, allow_null=True)
    currency = serializers.CharField(required=False, allow_blank=True, max_length=3)
    catalog_version = serializers.CharField(required=False, allow_blank=True, max_length=64)

    def validate_lines(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value


class OfflineOrderAddLinesPayloadSerializer(serializers.Serializer):
    """Payload for ``operation_type`` = ``order_add_lines`` (open order at same outlet)."""

    order_id = serializers.UUIDField(required=False, allow_null=True)
    lines = OrderLineInputSerializer(many=True)
    catalog_version = serializers.CharField(required=False, allow_blank=True, max_length=64)

    def validate_lines(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value


class OfflineQueueCreateSerializer(serializers.Serializer):
    outlet = serializers.UUIDField()
    client_mutation_id = serializers.CharField(max_length=128)
    operation_type = serializers.ChoiceField(
        choices=["order_payment", "order_create", "order_add_lines"],
    )
    payload = serializers.DictField()

    def validate(self, attrs: dict) -> dict:
        op = attrs["operation_type"]
        payload = attrs["payload"]
        if op == "order_payment":
            oid = payload.get("order_id")
            idem = (payload.get("idempotency_key") or "").strip()
            method = payload.get("method")
            deferred_oid = self.context.get("allow_deferred_order_id_for_payment", False)
            if not idem or not method:
                raise serializers.ValidationError(
                    {"payload": "order_payment requires idempotency_key, method, and amount."}
                )
            if payload.get("amount") is None:
                raise serializers.ValidationError({"payload": "order_payment requires amount."})
            if not deferred_oid and not oid:
                raise serializers.ValidationError(
                    {
                        "payload": (
                            "order_payment requires order_id on single sync, "
                            "or use batch depends_on without order_id."
                        )
                    }
                )
            OrderPaySerializer(data=payload).is_valid(raise_exception=True)
            for name in ("workstation_id", "shift_id"):
                if payload.get(name) is not None:
                    payload[name] = str(serializers.UUIDField().run_validation(payload[name]))
            return attrs
        if op == "order_create":
            ser = OfflineOrderCreatePayloadSerializer(data=payload)
            ser.is_valid(raise_exception=True)
            attrs["payload"] = ser.validated_data
            return attrs
        if op == "order_add_lines":
            ser = OfflineOrderAddLinesPayloadSerializer(data=payload)
            ser.is_valid(raise_exception=True)
            p = ser.validated_data
            if not p.get("order_id") and not self.context.get(
                "allow_deferred_order_id_for_add_lines", False
            ):
                raise serializers.ValidationError(
                    {
                        "payload": (
                            "order_add_lines requires order_id on single sync, "
                            "or use batch depends_on without order_id."
                        )
                    }
                )
            attrs["payload"] = p
            return attrs
        raise serializers.ValidationError({"operation_type": "Invalid operation type."})


class OfflineQueueBatchOperationSerializer(serializers.Serializer):
    """One batch entry: same as single sync, plus optional ``depends_on`` (prior index)."""

    outlet = serializers.UUIDField()
    client_mutation_id = serializers.CharField(max_length=128)
    operation_type = serializers.ChoiceField(
        choices=["order_payment", "order_create", "order_add_lines"],
    )
    payload = serializers.DictField()
    depends_on = serializers.IntegerField(required=False, min_value=0, max_value=49)

    def validate(self, attrs: dict) -> dict:
        dep = attrs.get("depends_on")
        op = attrs["operation_type"]
        if dep is not None and op not in ("order_add_lines", "order_payment"):
            raise serializers.ValidationError(
                {
                    "depends_on": "depends_on is only allowed for order_add_lines or order_payment.",
                }
            )
        inner = OfflineQueueCreateSerializer(
            data={
                "outlet": attrs["outlet"],
                "client_mutation_id": attrs["client_mutation_id"],
                "operation_type": attrs["operation_type"],
                "payload": attrs["payload"],
            },
            context={
                **self.context,
                "allow_deferred_order_id_for_add_lines": dep is not None and op == "order_add_lines",
                "allow_deferred_order_id_for_payment": dep is not None and op == "order_payment",
            },
        )
        inner.is_valid(raise_exception=True)
        attrs["outlet"] = inner.validated_data["outlet"]
        attrs["client_mutation_id"] = inner.validated_data["client_mutation_id"]
        attrs["operation_type"] = inner.validated_data["operation_type"]
        attrs["payload"] = inner.validated_data["payload"]
        if dep is not None and attrs["payload"].get("order_id"):
            raise serializers.ValidationError(
                {
                    "payload": (
                        "Do not include order_id when depends_on is set; "
                        "it is filled from the prior result."
                    )
                }
            )
        return attrs


class OfflineQueueBatchSerializer(serializers.Serializer):
    """Drain multiple offline mutations in one request; each keeps its own ``client_mutation_id``."""

    operations = OfflineQueueBatchOperationSerializer(many=True)

    def validate_operations(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("At least one operation is required.")
        if len(value) > 50:
            raise serializers.ValidationError("At most 50 operations per batch.")
        return value


class OfflineQueuedOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfflineQueuedOperation
        fields = [
            "id",
            "client_mutation_id",
            "operation_type",
            "status",
            "error_message",
            "applied_payment_id",
            "applied_order_id",
            "created_at",
        ]
        read_only_fields = fields
