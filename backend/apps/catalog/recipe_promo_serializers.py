from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.tenants.models import Outlet

from .models import MenuCategory, MenuItem, MenuItemRecipeLine, ProductFamily, Promotion


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
            "menu_item",
            "product_family",
            "category",
            "brand",
            "discount_percent",
            "discount_amount",
            "min_order_subtotal",
            "min_target_quantity",
            "coupon_code",
            "max_redemptions",
            "max_redemptions_per_customer",
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

        tenant = self.context["request"].tenant
        menu_item = attrs.get("menu_item", inst.menu_item if inst else None)
        product_family = attrs.get("product_family", inst.product_family if inst else None)
        category = attrs.get("category", inst.category if inst else None)
        brand = (attrs.get("brand", inst.brand if inst else "") or "").strip()
        if sum(bool(value) for value in (menu_item, product_family, category, brand)) > 1:
            raise serializers.ValidationError(
                "Choose only one promotion target: product, product family, category, or brand."
            )
        if menu_item is not None and menu_item.tenant_id != tenant.pk:
            raise serializers.ValidationError({"menu_item": "Choose a product from this business."})
        if product_family is not None and product_family.tenant_id != tenant.pk:
            raise serializers.ValidationError({"product_family": "Choose a product family from this business."})
        if category is not None and category.tenant_id != tenant.pk:
            raise serializers.ValidationError({"category": "Choose a category from this business."})
        attrs["brand"] = brand

        coupon_code = (attrs.get("coupon_code", inst.coupon_code if inst else "") or "").strip()
        if coupon_code:
            qs = Promotion.objects.filter(
                tenant=tenant,
                coupon_code__iexact=coupon_code,
            )
            if inst is not None:
                qs = qs.exclude(pk=inst.pk)
            if qs.exists():
                raise serializers.ValidationError({"coupon_code": "This coupon code is already in use."})
        attrs["coupon_code"] = coupon_code

        total_limit = attrs.get("max_redemptions", inst.max_redemptions if inst else None)
        customer_limit = attrs.get(
            "max_redemptions_per_customer",
            inst.max_redemptions_per_customer if inst else None,
        )
        if total_limit is not None and customer_limit is not None and customer_limit > total_limit:
            raise serializers.ValidationError({
                "max_redemptions_per_customer": "Per-customer limit cannot exceed the total redemption limit."
            })
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
