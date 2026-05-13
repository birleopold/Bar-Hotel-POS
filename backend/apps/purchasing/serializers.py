from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.access.outlets import outlet_belongs_to_membership
from apps.catalog.models import MenuItem
from apps.tenants.models import Outlet

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier


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
            "unit_cost",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineReadSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)

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
            "reference",
            "expected_date",
            "notes",
            "created_by",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PurchaseOrderLineInputSerializer(serializers.Serializer):
    menu_item = serializers.UUIDField()
    quantity_ordered = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0.001")
    )
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

        attrs["_supplier"] = supplier
        attrs["_outlet"] = outlet
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        tenant = request.tenant
        lines_in = validated_data["lines"]
        seen_items: set = set()
        line_objects = []

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
            line_objects.append(
                {
                    "menu_item": item,
                    "quantity_ordered": row["quantity_ordered"],
                    "unit_cost": row.get("unit_cost"),
                }
            )

        po = PurchaseOrder.objects.create(
            tenant=tenant,
            supplier=validated_data["_supplier"],
            outlet=validated_data["_outlet"],
            reference=(validated_data.get("reference") or "")[:128],
            expected_date=validated_data.get("expected_date"),
            notes=validated_data.get("notes") or "",
            created_by=request.user,
            status=PurchaseOrderStatus.DRAFT,
        )
        for lo in line_objects:
            PurchaseOrderLine.objects.create(
                purchase_order=po,
                menu_item=lo["menu_item"],
                quantity_ordered=lo["quantity_ordered"],
                unit_cost=lo["unit_cost"],
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
            if not inst.lines.exists():
                raise serializers.ValidationError("Add line items before sending.")
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
        max_digits=14, decimal_places=3, min_value=Decimal("0")
    )


class ReceivePurchaseOrderSerializer(serializers.Serializer):
    lines = ReceiveLineSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("At least one line entry is required.")
        return value
