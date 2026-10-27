from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.access.outlets import outlet_belongs_to_membership
from apps.catalog.models import MenuItem, ProductPackage
from apps.catalog.packaging import to_stock_units
from apps.tenants.models import Outlet

from .models import PurchaseApprovalStatus, PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, PurchaseReceipt, PurchaseReceiptLine, Supplier, SupplierPayment, SupplierPaymentMethod, SupplierInvoice
from .supplier_catalog import supplier_product_reference, suggested_supplier_unit_cost


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id",
            "tenant",
            "name",
            "email",
            "phone",
            "address_line",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "tenant", "created_at", "updated_at")


class PurchaseOrderLineReadSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    quantity_remaining = serializers.SerializerMethodField()

    @extend_schema_field(serializers.DecimalField(max_digits=14, decimal_places=3))
    def get_quantity_remaining(self, obj):
        return obj.quantity_remaining

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "menu_item",
            "menu_item_name",
            "quantity_ordered",
            "quantity_received",
            "quantity_remaining",
            "units_per_carton_snapshot",
            "product_package",
            "package_name_snapshot",
            "package_units_snapshot",
            "package_quantity_ordered",
            "unit_cost",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PurchaseReceiptLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="purchase_order_line.menu_item.name", read_only=True)

    class Meta:
        model = PurchaseReceiptLine
        fields = (
            "id", "purchase_order_line", "item_name", "quantity_received",
            "cartons_received", "packages_received", "unit_cost_snapshot",
            "landed_unit_cost_snapshot", "landed_cost_allocated",
        )
        read_only_fields = fields


class PurchaseReceiptSerializer(serializers.ModelSerializer):
    lines = PurchaseReceiptLineSerializer(many=True, read_only=True)
    received_by_email = serializers.EmailField(source="received_by.email", read_only=True, allow_null=True)

    class Meta:
        model = PurchaseReceipt
        fields = (
            "id", "delivery_reference", "note", "discrepancy_note",
            "shipping_cost", "duty_cost", "landed_cost_allocation",
            "received_by", "received_by_email", "created_at", "lines",
        )
        read_only_fields = fields


class SupplierPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierPayment
        fields = ("id", "invoice", "amount", "method", "reference", "created_at")
        read_only_fields = fields


class RecordSupplierPaymentSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=SupplierPaymentMethod.choices)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=128, default="")


class LinkSupplierPaymentInvoiceSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    note = serializers.CharField(min_length=12, max_length=512, trim_whitespace=True)


class SupplierInvoiceLineInputSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class RecordSupplierReturnSerializer(serializers.Serializer):
    receipt_line_id = serializers.UUIDField()
    reference = serializers.CharField(max_length=128)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    note = serializers.CharField(min_length=12, max_length=512)


class RecordSupplierInvoiceSerializer(serializers.Serializer):
    lines = SupplierInvoiceLineInputSerializer(many=True, required=False)
    reference = serializers.CharField(max_length=128, trim_whitespace=True)
    invoice_date = serializers.DateField()
    due_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=512, default="")


class RecordSupplierCreditNoteSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    reference = serializers.CharField(max_length=128, trim_whitespace=True)
    credit_date = serializers.DateField()
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"),
    )
    reason = serializers.CharField(min_length=12, max_length=512, trim_whitespace=True)


class SupplierInvoiceReadSerializer(serializers.ModelSerializer):
    matching_status = serializers.SerializerMethodField()
    matched_lines = serializers.SerializerMethodField()

    def get_matching_status(self, obj: SupplierInvoice) -> str:
        return "three_way_matched" if obj.matched_lines.exists() else "legacy_unmatched"

    def get_matched_lines(self, obj: SupplierInvoice) -> list[dict[str, str]]:
        return [{"line_id": str(line.purchase_order_line_id), "quantity": str(line.quantity),
                 "unit_cost": str(line.unit_cost), "amount": str(line.amount)}
                for line in obj.matched_lines.all()]

    credited_amount = serializers.SerializerMethodField()
    linked_payments_amount = serializers.SerializerMethodField()
    unlinked_payment_warning = serializers.SerializerMethodField()
    unpaid_amount = serializers.SerializerMethodField()
    overdue_days = serializers.SerializerMethodField()

    @staticmethod
    def _numbers(obj: SupplierInvoice) -> tuple[Decimal, Decimal, Decimal]:
        credited = sum((entry.amount for entry in obj.credits.all()), Decimal("0"))
        paid = sum((entry.amount for entry in obj.allocated_payments.all()), Decimal("0"))
        return credited, paid, max(Decimal("0"), obj.amount - credited - paid)

    def get_credited_amount(self, obj: SupplierInvoice) -> str:
        return f"{self._numbers(obj)[0]:.2f}"

    def get_linked_payments_amount(self, obj: SupplierInvoice) -> str:
        return f"{self._numbers(obj)[1]:.2f}"

    def get_unlinked_payment_warning(self, obj: SupplierInvoice) -> bool:
        return obj.purchase_order.payments.filter(invoice__isnull=True).exists()

    def get_unpaid_amount(self, obj: SupplierInvoice) -> str | None:
        if self.get_unlinked_payment_warning(obj):
            return None  # Never pretend an unattributed PO payment belongs to this invoice.
        return f"{self._numbers(obj)[2]:.2f}"

    def get_overdue_days(self, obj: SupplierInvoice) -> int | None:
        from django.utils import timezone
        if self.get_unlinked_payment_warning(obj):
            return None
        due = self._numbers(obj)[2]
        return max(0, (timezone.localdate() - obj.due_date).days) if due > 0 else 0

    class Meta:
        model = SupplierInvoice
        fields = (
            "id", "reference", "invoice_date", "due_date", "amount",
            "matching_status", "matched_lines", "credited_amount", "linked_payments_amount", "unlinked_payment_warning",
            "unpaid_amount", "overdue_days", "note", "created_at",
        )
        read_only_fields = fields


class ConfirmMissingUnitCostSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineReadSerializer(many=True, read_only=True)
    sourcing = serializers.SerializerMethodField()
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)
    receipts = PurchaseReceiptSerializer(many=True, read_only=True)
    payments = SupplierPaymentSerializer(many=True, read_only=True)
    invoices = SupplierInvoiceReadSerializer(many=True, read_only=True)

    def get_sourcing(self, obj):
        try:
            quote = obj.source_supplier_quote
        except ObjectDoesNotExist:
            return None
        return {
            "supplier_quote_id": str(quote.pk),
            "supplier_quote_reference": quote.reference,
            "rfq_id": str(quote.rfq_id),
            "rfq_reference": quote.rfq.reference,
            "quoted_shipping_cost": str(quote.shipping_cost),
            "quoted_other_cost": str(quote.other_cost),
        }

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "tenant",
            "supplier",
            "supplier_name",
            "outlet",
            "outlet_name",
            "status",
            "approval_status",
            "sourcing",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "reference",
            "expected_date",
            "notes",
            "created_by",
            "lines",
            "receipts",
            "payments",
            "invoices",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PurchaseOrderLineInputSerializer(serializers.Serializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("quantity_ordered") and not attrs.get("cartons") and not attrs.get("package_count"):
            raise serializers.ValidationError("Enter loose units, cartons or packages.")
        if attrs.get("cartons") and attrs.get("package_count"):
            raise serializers.ValidationError("Use either the selected package or legacy cartons on one line, not both.")
        if attrs.get("package_count") and not attrs.get("product_package"):
            raise serializers.ValidationError({"product_package": "Choose the package being ordered."})
        if attrs.get("product_package") and not attrs.get("package_count"):
            raise serializers.ValidationError({"package_count": "Enter how many selected packages to order."})
        return attrs

    menu_item = serializers.UUIDField()
    quantity_ordered = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0"), required=False, default=Decimal("0"),
    )
    cartons = serializers.IntegerField(required=False, min_value=1)
    product_package = serializers.UUIDField(required=False, allow_null=True)
    package_count = serializers.IntegerField(required=False, min_value=1)
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal("0"),
    )


class PurchaseOrderCreateSerializer(serializers.Serializer):
    supplier = serializers.UUIDField()
    outlet = serializers.UUIDField()
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    expected_date = serializers.DateField(required=False, allow_null=True)
    needed_by = serializers.DateField(required=False, allow_null=True)
    request_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=512,
        default="",
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = PurchaseOrderLineInputSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        tenant = request.tenant
        membership = request.tenant_membership

        supplier = Supplier.objects.filter(id=attrs["supplier"], tenant_id=tenant.id).first()
        if supplier is None:
            raise serializers.ValidationError({"supplier": "Invalid supplier for this tenant."})

        outlet = Outlet.objects.filter(
            id=attrs["outlet"], site__tenant_id=tenant.id, is_active=True
        ).first()
        if outlet is None:
            raise serializers.ValidationError({"outlet": "Invalid outlet for this tenant."})
        if not outlet_belongs_to_membership(membership, outlet.id):
            raise serializers.ValidationError(
                {"outlet": "You cannot create a PO for this outlet."}
            )

        for row in attrs["lines"]:
            item = MenuItem.objects.filter(
                pk=row["menu_item"], tenant_id=tenant.pk, is_active=True,
                track_inventory=True,
            ).first()
            if item is None:
                raise serializers.ValidationError({"lines": "Choose an active tracked product."})
            if item.units_per_carton > 1 and item.unit_of_measure != "each":
                raise serializers.ValidationError({"lines": "Cartons must be configured for a piece-based item."})
            package = None
            if row.get("product_package"):
                package = ProductPackage.objects.filter(
                    pk=row["product_package"],
                    tenant_id=tenant.pk,
                    menu_item=item,
                    is_active=True,
                    is_purchasable=True,
                ).first()
                if package is None:
                    raise serializers.ValidationError({"lines": f"Choose an active purchasable package for {item.name}."})
            legacy_units = to_stock_units(
                units=row["quantity_ordered"], cartons=row.get("cartons", 0),
                units_per_carton=item.units_per_carton,
                allow_zero=bool(package),
            )
            if package:
                package_units = (Decimal(row["package_count"]) * package.units_per_package).quantize(Decimal("0.001"))
                total = legacy_units + package_units
                if total <= 0 or total > Decimal("99999999999.999"):
                    raise serializers.ValidationError({"lines": f"Ordered quantity for {item.name} is outside stock limits."})
        attrs["_supplier"] = supplier
        attrs["_outlet"] = outlet
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        tenant = request.tenant
        lines_in = validated_data["lines"]
        seen_items: set = set()
        line_objects = []
        expected_lead_days = []

        for row in lines_in:
            mid = row["menu_item"]
            if mid in seen_items:
                raise serializers.ValidationError(
                    {"lines": "Duplicate menu_item in lines is not allowed."}
                )
            seen_items.add(mid)
            item = MenuItem.objects.filter(
                id=mid, tenant_id=tenant.id, is_active=True
            ).first()
            if item is None:
                raise serializers.ValidationError({"lines": f"Invalid menu_item {mid}."})
            if not item.track_inventory:
                raise serializers.ValidationError(
                    {"lines": f"Item {item.name} must have track_inventory enabled."}
                )
            if item.units_per_carton > 1 and item.unit_of_measure != "each":
                raise serializers.ValidationError({"lines": f"Cartons for {item.name} require piece units."})
            package = None
            if row.get("product_package"):
                package = ProductPackage.objects.filter(
                    pk=row["product_package"],
                    tenant_id=tenant.id,
                    menu_item=item,
                    is_active=True,
                    is_purchasable=True,
                ).first()
                if package is None:
                    raise serializers.ValidationError({"lines": f"Invalid package for {item.name}."})
            ordered_units = to_stock_units(
                units=row["quantity_ordered"], cartons=row.get("cartons", 0),
                units_per_carton=item.units_per_carton,
                allow_zero=bool(package),
            )
            if package:
                ordered_units += (Decimal(row["package_count"]) * package.units_per_package).quantize(Decimal("0.001"))
                if ordered_units > Decimal("99999999999.999"):
                    raise serializers.ValidationError({"lines": f"Ordered quantity for {item.name} exceeds stock limits."})
            relation = supplier_product_reference(
                tenant_id=tenant.id,
                supplier_id=validated_data["_supplier"].id,
                menu_item_id=item.id,
                product_package_id=package.id if package else None,
            )
            if (
                relation is not None
                and relation.minimum_order_quantity is not None
                and ordered_units < relation.minimum_order_quantity
            ):
                raise serializers.ValidationError({
                    "lines": (
                        f"{item.name} requires at least "
                        f"{relation.minimum_order_quantity} base units from "
                        f"{validated_data['_supplier'].name}."
                    )
                })
            if relation is not None and relation.expected_lead_days is not None:
                expected_lead_days.append(relation.expected_lead_days)

            unit_cost = row.get("unit_cost")
            if unit_cost is None:
                unit_cost, _cost_source = suggested_supplier_unit_cost(
                    tenant_id=tenant.id,
                    supplier_id=validated_data["_supplier"].id,
                    menu_item_id=item.id,
                    product_package_id=package.id if package else None,
                    ordered_quantity=ordered_units,
                )
            line_objects.append({
                "menu_item": item, "quantity_ordered": ordered_units,
                "unit_cost": unit_cost,
                "units_per_carton_snapshot": item.units_per_carton,
                "product_package": package,
                "package_name_snapshot": package.name if package else "",
                "package_units_snapshot": package.units_per_package if package else None,
                "package_quantity_ordered": row.get("package_count", 0) if package else 0,
            })

        auto_approve = bool(self.context.get("auto_approve"))
        po = PurchaseOrder.objects.create(
            tenant=tenant,
            supplier=validated_data["_supplier"],
            outlet=validated_data["_outlet"],
            reference=(validated_data.get("reference") or "")[:128],
            expected_date=(
                validated_data.get("expected_date")
                or (
                    timezone.localdate() + timedelta(days=max(expected_lead_days))
                    if expected_lead_days else None
                )
            ),
            needed_by=validated_data.get("needed_by"),
            request_reason=(validated_data.get("request_reason") or "").strip(),
            notes=validated_data.get("notes") or "",
            created_by=request.user,
            status=PurchaseOrderStatus.DRAFT,
            approval_status=(
                PurchaseApprovalStatus.APPROVED
                if auto_approve else PurchaseApprovalStatus.PENDING
            ),
            reviewed_by=request.user if auto_approve else None,
            reviewed_at=timezone.now() if auto_approve else None,
            review_note="Manager-created draft" if auto_approve else "",
        )
        for lo in line_objects:
            PurchaseOrderLine.objects.create(
                purchase_order=po,
                menu_item=lo["menu_item"],
                quantity_ordered=lo["quantity_ordered"],
                unit_cost=lo["unit_cost"],
                units_per_carton_snapshot=lo["units_per_carton_snapshot"],
                product_package=lo["product_package"],
                package_name_snapshot=lo["package_name_snapshot"],
                package_units_snapshot=lo["package_units_snapshot"],
                package_quantity_ordered=lo["package_quantity_ordered"],
            )
        return po


class PurchaseOrderStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrder
        fields = ("status",)

    def validate_status(self, value):
        inst = self.instance
        if inst is None:
            return value
        if inst.status == PurchaseOrderStatus.CANCELLED:
            raise serializers.ValidationError("Cancelled purchase orders cannot change status.")
        if value == inst.status:
            return value
        if value == PurchaseOrderStatus.SENT:
            if inst.status != PurchaseOrderStatus.DRAFT:
                raise serializers.ValidationError("Only draft orders can be sent.")
            if inst.approval_status != PurchaseApprovalStatus.APPROVED:
                raise serializers.ValidationError(
                    "This purchase request must be manager-approved before it can be sent."
                )
            if not inst.lines.exists():
                raise serializers.ValidationError("Add line items before sending.")
            for line in inst.lines.select_related("menu_item", "product_package").all():
                relation = supplier_product_reference(
                    tenant_id=inst.tenant_id,
                    supplier_id=inst.supplier_id,
                    menu_item_id=line.menu_item_id,
                    product_package_id=line.product_package_id,
                )
                if (
                    relation is not None
                    and relation.minimum_order_quantity is not None
                    and line.quantity_ordered < relation.minimum_order_quantity
                ):
                    raise serializers.ValidationError(
                        f"{line.menu_item.name} requires at least "
                        f"{relation.minimum_order_quantity} base units from this supplier."
                    )
        elif value == PurchaseOrderStatus.CANCELLED:
            if inst.status == PurchaseOrderStatus.RECEIVED:
                raise serializers.ValidationError("Cannot cancel a fully received order.")
            if any(l.quantity_received > 0 for l in inst.lines.all()):
                raise serializers.ValidationError(
                    "Cannot cancel after goods have been received."
                )
        else:
            raise serializers.ValidationError("Invalid status for this transition.")
        return value


class ReceiveLineSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0"), required=False, default=Decimal("0"),
    )
    cartons = serializers.IntegerField(required=False, min_value=1)
    packages = serializers.IntegerField(required=False, min_value=1)
    serial_numbers = serializers.ListField(
        child=serializers.CharField(max_length=128, trim_whitespace=True),
        required=False,
        default=list,
    )
    batch_code = serializers.CharField(required=False, allow_blank=True, max_length=128)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    received_at = serializers.DateField(required=False)
    landed_cost_amount = serializers.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
    )

    def validate(self, attrs):
        if attrs.get("expiry_date") and not (attrs.get("batch_code") or "").strip():
            raise serializers.ValidationError({"batch_code": "A batch code is required for an expiry date."})
        if attrs.get("cartons") and attrs.get("packages"):
            raise serializers.ValidationError("Use either packages or cartons on one receiving row, not both.")
        return attrs


class ReceivePurchaseOrderSerializer(serializers.Serializer):
    lines = ReceiveLineSerializer(many=True)
    discrepancy_note = serializers.CharField(required=False, allow_blank=True, max_length=512, default="")
    delivery_reference = serializers.CharField(required=False, allow_blank=True, max_length=128, default="")
    note = serializers.CharField(required=False, allow_blank=True, max_length=512, default="")
    shipping_cost = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"),
        required=False, default=Decimal("0"),
    )
    duty_cost = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"),
        required=False, default=Decimal("0"),
    )
    landed_cost_allocation = serializers.ChoiceField(
        choices=PurchaseReceipt.LandedCostAllocation.choices,
        required=False,
        default=PurchaseReceipt.LandedCostAllocation.EXCLUDE,
    )

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line entry is required.")
        return value
