from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.tenants.models import Outlet

from .models import MenuItem, MenuItemRecipeLine, Promotion


class MenuItemRecipeLineReadSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient_item.name", read_only=True)

    class Meta:
        model = MenuItemRecipeLine
        fields = [
            "id",
            "ingredient_item",
            "ingredient_name",
            "quantity_per_unit",
            "created_at",
        ]
        read_only_fields = fields


class RecipeLineInputSerializer(serializers.Serializer):
    ingredient_item = serializers.UUIDField()
    quantity_per_unit = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )


class MenuItemRecipeReplaceSerializer(serializers.Serializer):
    lines = RecipeLineInputSerializer(many=True)

    def save(self, **kwargs):
        parent_item: MenuItem = kwargs["parent_item"]
        tenant_id = parent_item.tenant_id
        lines_in = self.validated_data.get("lines", [])
        seen: set = set()
        to_create: list[MenuItemRecipeLine] = []
        for row in lines_in:
            iid = row["ingredient_item"]
            if iid in seen:
                raise serializers.ValidationError({"lines": "Duplicate ingredient in recipe."})
            seen.add(iid)
            if iid == parent_item.id:
                raise serializers.ValidationError({"lines": "A menu item cannot be an ingredient of itself."})
            ing = MenuItem.objects.filter(id=iid, tenant_id=tenant_id, is_active=True).first()
            if ing is None:
                raise serializers.ValidationError({"lines": f"Invalid ingredient menu item {iid}."})
            to_create.append(
                MenuItemRecipeLine(
                    parent_item=parent_item,
                    ingredient_item=ing,
                    quantity_per_unit=row["quantity_per_unit"],
                )
            )
        with transaction.atomic():
            parent_item.recipe_lines.all().delete()
            MenuItemRecipeLine.objects.bulk_create(to_create)
        return parent_item


class PromotionSerializer(serializers.ModelSerializer):
    outlet_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        help_text="Limit to these outlets; omit or empty for all outlets.",
    )

    class Meta:
        model = Promotion
        fields = [
            "id",
            "tenant",
            "name",
            "discount_percent",
            "discount_amount",
            "min_order_subtotal",
            "starts_at",
            "ends_at",
            "is_active",
            "outlets",
            "outlet_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "tenant", "outlets", "created_at", "updated_at")

    def validate(self, attrs):
        inst = self.instance
        pct = attrs["discount_percent"] if "discount_percent" in attrs else (
            inst.discount_percent if inst else None
        )
        amt = attrs["discount_amount"] if "discount_amount" in attrs else (
            inst.discount_amount if inst else None
        )
        has_pct = pct is not None
        has_amt = amt is not None
        if has_pct == has_amt:
            raise serializers.ValidationError(
                "Set exactly one of discount_percent or discount_amount."
            )
        return attrs

    def create(self, validated_data):
        outlet_ids = validated_data.pop("outlet_ids", None)
        tenant = self.context["request"].tenant
        validated_data["tenant"] = tenant
        promo = super().create(validated_data)
        self._sync_outlets(promo, outlet_ids)
        return promo

    def update(self, instance, validated_data):
        outlet_ids = validated_data.pop("outlet_ids", serializers.empty)
        promo = super().update(instance, validated_data)
        if outlet_ids is not serializers.empty:
            self._sync_outlets(promo, outlet_ids)
        return promo

    def _sync_outlets(self, promo: Promotion, outlet_ids: list | None) -> None:
        if outlet_ids is None:
            return
        tenant_id = promo.tenant_id
        outlets = list(Outlet.objects.filter(id__in=outlet_ids, site__tenant_id=tenant_id))
        if len(outlets) != len(set(outlet_ids)):
            raise serializers.ValidationError({"outlet_ids": "Invalid outlet list for this tenant."})
        promo.outlets.set(outlets)
