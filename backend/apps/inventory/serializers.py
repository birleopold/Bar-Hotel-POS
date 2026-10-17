from decimal import Decimal

from rest_framework import serializers

from apps.access.outlets import outlet_belongs_to_membership
from apps.catalog.models import MenuItem
from apps.catalog.packaging import to_stock_units
from apps.tenants.models import Outlet

from .models import (
    StockBalance,
    StockShelfLocation,
    StockCountLine,
    StockCountSession,
    StockMovement,
    StockReason,
)


class ShelfLocationWriteSerializer(serializers.Serializer):
    outlet_id = serializers.UUIDField()
    menu_item_id = serializers.UUIDField()
    aisle = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")
    shelf = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")
    bin_code = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")
    note = serializers.CharField(max_length=160, allow_blank=True, required=False, default="")


class ShelfLocationReadSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="menu_item.name", read_only=True)
    item_sku = serializers.CharField(source="menu_item.sku", read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)

    class Meta:
        model = StockShelfLocation
        fields = (
            "id", "outlet", "outlet_name", "menu_item", "item_name", "item_sku",
            "aisle", "shelf", "bin_code", "note", "updated_by", "updated_at",
        )
        read_only_fields = fields


class StockBalanceSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    menu_item_sku = serializers.CharField(source="menu_item.sku", read_only=True)
    menu_item_barcode = serializers.CharField(source="menu_item.barcode", read_only=True)
    unit_of_measure = serializers.CharField(source="menu_item.unit_of_measure", read_only=True)
    track_inventory = serializers.BooleanField(source="menu_item.track_inventory", read_only=True)
    reorder_level = serializers.DecimalField(
        source="menu_item.reorder_level",
        max_digits=14,
        decimal_places=3,
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = StockBalance
        fields = [
            "id",
            "outlet",
            "menu_item",
            "menu_item_name",
            "menu_item_sku",
            "menu_item_barcode",
            "unit_of_measure",
            "track_inventory",
            "reorder_level",
            "quantity",
            "updated_at",
        ]
        read_only_fields = (
            "id",
            "outlet",
            "menu_item",
            "menu_item_name",
            "menu_item_sku",
            "menu_item_barcode",
            "unit_of_measure",
            "track_inventory",
            "reorder_level",
            "quantity",
            "updated_at",
        )


class StockMovementSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "outlet",
            "menu_item",
            "menu_item_name",
            "quantity_change",
            "reason",
            "transfer_batch",
            "purchase_order",
            "order",
            "note",
            "created_by",
            "created_at",
        ]
        read_only_fields = (
            "id",
            "outlet",
            "menu_item",
            "menu_item_name",
            "quantity_change",
            "reason",
            "transfer_batch",
            "purchase_order",
            "order",
            "note",
            "created_by",
            "created_at",
        )


class StockMovementWriteSerializer(serializers.Serializer):
    outlet = serializers.UUIDField()
    menu_item = serializers.UUIDField()
    quantity_change = serializers.DecimalField(max_digits=14, decimal_places=3)
    reason = serializers.ChoiceField(choices=StockReason.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict) -> dict:
        reason = attrs["reason"]
        delta: Decimal = attrs["quantity_change"]
        if reason == StockReason.RECEIVE and delta <= 0:
            raise serializers.ValidationError(
                {"quantity_change": "Must be positive for receive."}
            )
        if reason == StockReason.ADJUST_IN and delta <= 0:
            raise serializers.ValidationError(
                {"quantity_change": "Must be positive for adjust-in."}
            )
        if reason == StockReason.ADJUST_OUT and delta >= 0:
            raise serializers.ValidationError(
                {"quantity_change": "Must be negative for adjust-out."}
            )
        if reason == StockReason.WASTE and delta >= 0:
            raise serializers.ValidationError({"quantity_change": "Must be negative for waste."})
        if reason == StockReason.SALE:
            raise serializers.ValidationError({"reason": "Sales are recorded automatically when an order is paid."})
        if reason == StockReason.RECIPE:
            raise serializers.ValidationError(
                {"reason": "Recipe consumption is recorded when paying for recipe-enabled menu items."}
            )
        if reason in (StockReason.TRANSFER_OUT, StockReason.TRANSFER_IN):
            raise serializers.ValidationError(
                {"reason": "Use POST /stock/transfers/ for inter-outlet transfers."}
            )
        if reason == StockReason.PHYSICAL_COUNT:
            raise serializers.ValidationError(
                {"reason": "Use stock count sessions to post physical count adjustments."}
            )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        tenant = request.tenant
        outlet = Outlet.objects.filter(
            id=validated_data["outlet"],
            site__tenant_id=tenant.id,
            is_active=True,
        ).first()
        if outlet is None:
            raise serializers.ValidationError({"outlet": "Invalid outlet for this tenant."})
        if not outlet_belongs_to_membership(request.tenant_membership, outlet.id):
            raise serializers.ValidationError({"outlet": "You cannot adjust stock for this outlet."})
        menu_item = MenuItem.objects.filter(
            id=validated_data["menu_item"],
            tenant_id=tenant.id,
            is_active=True,
        ).first()
        if menu_item is None:
            raise serializers.ValidationError({"menu_item": "Invalid menu item for this tenant."})
        if not menu_item.track_inventory:
            raise serializers.ValidationError(
                {"menu_item": "Enable track_inventory on the item to manage stock."}
            )

        from .services import apply_manual_stock_change

        return apply_manual_stock_change(
            tenant_id=tenant.id,
            outlet=outlet,
            menu_item=menu_item,
            quantity_change=validated_data["quantity_change"],
            reason=validated_data["reason"],
            user=request.user,
            note=validated_data.get("note", ""),
        )


class StockTransferSerializer(serializers.Serializer):
    from_outlet = serializers.UUIDField()
    to_outlet = serializers.UUIDField()
    menu_item = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0"), required=False, default=Decimal("0"))
    cartons = serializers.IntegerField(required=False, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    dispatch_only = serializers.BooleanField(required=False, default=False)

    def create(self, validated_data):
        from .services import execute_stock_transfer

        request = self.context["request"]
        tenant = request.tenant
        membership = request.tenant_membership
        from_outlet = Outlet.objects.filter(
            id=validated_data["from_outlet"],
            site__tenant_id=tenant.id,
            is_active=True,
        ).first()
        if from_outlet is None:
            raise serializers.ValidationError({"from_outlet": "Invalid source outlet."})
        to_outlet = Outlet.objects.filter(
            id=validated_data["to_outlet"],
            site__tenant_id=tenant.id,
            is_active=True,
        ).first()
        if to_outlet is None:
            raise serializers.ValidationError({"to_outlet": "Invalid destination outlet."})
        menu_item = MenuItem.objects.filter(
            id=validated_data["menu_item"],
            tenant_id=tenant.id,
            is_active=True,
        ).first()
        if menu_item is None:
            raise serializers.ValidationError({"menu_item": "Invalid menu item."})

        return execute_stock_transfer(
            staged=validated_data.get("dispatch_only", False),
            tenant_id=tenant.id,
            membership=membership,
            from_outlet=from_outlet,
            to_outlet=to_outlet,
            menu_item=menu_item,
            quantity=to_stock_units(
                units=validated_data["quantity"], cartons=validated_data.get("cartons", 0),
                units_per_carton=menu_item.units_per_carton,
            ),
            user=request.user,
            note=validated_data.get("note", ""),
        )


class StockCountLineSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    menu_item_sku = serializers.CharField(source="menu_item.sku", read_only=True)
    menu_item_barcode = serializers.CharField(source="menu_item.barcode", read_only=True)

    class Meta:
        model = StockCountLine
        fields = [
            "id",
            "menu_item",
            "menu_item_name",
            "menu_item_sku",
            "menu_item_barcode",
            "counted_quantity",
            "system_quantity_before",
            "variance",
        ]
        read_only_fields = fields


class StockCountSessionSerializer(serializers.ModelSerializer):
    lines = StockCountLineSerializer(many=True, read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)

    class Meta:
        model = StockCountSession
        fields = [
            "id",
            "outlet",
            "outlet_name",
            "status",
            "note",
            "created_by",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "completed_at",
            "created_at",
            "updated_at",
            "lines",
        ]
        read_only_fields = (
            "id",
            "outlet_name",
            "status",
            "created_by",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "completed_at",
            "created_at",
            "updated_at",
            "lines",
        )


class StockCountSessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockCountSession
        fields = ["outlet", "note"]

    def validate_outlet(self, value: Outlet) -> Outlet:
        request = self.context["request"]
        if value.site.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Outlet must belong to the current tenant.")
        if not outlet_belongs_to_membership(request.tenant_membership, value.id):
            raise serializers.ValidationError("You cannot start a stock count for this outlet.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["tenant"] = request.tenant
        validated_data["created_by"] = request.user
        return super().create(validated_data)


class StockCountLineInputSerializer(serializers.Serializer):
    menu_item = serializers.UUIDField()
    counted_quantity = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0"),
    )


class StockCountCompleteSerializer(serializers.Serializer):
    lines = StockCountLineInputSerializer(many=True)

    def validate_lines(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        ids = [row["menu_item"] for row in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate menu_item in lines.")
        return value
