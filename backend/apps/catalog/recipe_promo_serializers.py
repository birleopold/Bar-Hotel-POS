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
            "offer_type",
            "menu_item",
            "product_family",
            "category",
            "brand",
            "reward_menu_item",
            "reward_product_family",
            "reward_category",
            "reward_brand",
            "discount_percent",
            "discount_amount",
            "min_order_subtotal",
            "min_target_quantity",
            "coupon_code",
            "max_redemptions",
            "max_redemptions_per_customer",
            "buy_quantity",
            "get_quantity",
            "fixed_quantity",
            "fixed_bundle_amount",
            "max_uses_per_order",
            "starts_at",
            "ends_at",
            "schedule_weekdays",
            "schedule_start_time",
            "schedule_end_time",
            "is_active",
            "outlets",
            "outlet_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "tenant", "outlets", "created_at", "updated_at")

    def validate(self, attrs):
        inst = self.instance
        offer_type = attrs.get(
            "offer_type",
            inst.offer_type if inst else Promotion.OfferType.STANDARD,
        )
        pct = attrs["discount_percent"] if "discount_percent" in attrs else (
            inst.discount_percent if inst else None
        )
        amt = attrs["discount_amount"] if "discount_amount" in attrs else (
            inst.discount_amount if inst else None
        )
        buy_quantity = attrs.get("buy_quantity", inst.buy_quantity if inst else None)
        get_quantity = attrs.get("get_quantity", inst.get_quantity if inst else None)
        fixed_quantity = attrs.get(
            "fixed_quantity",
            inst.fixed_quantity if inst else None,
        )
        fixed_bundle_amount = attrs.get(
            "fixed_bundle_amount",
            inst.fixed_bundle_amount if inst else None,
        )
        max_uses_per_order = attrs.get(
            "max_uses_per_order",
            inst.max_uses_per_order if inst else None,
        )
        has_pct = pct is not None
        has_amt = amt is not None
        if offer_type == Promotion.OfferType.BUY_X_GET_Y:
            if has_pct or has_amt:
                raise serializers.ValidationError(
                    "Buy X Get Y uses buy/get quantities; leave amount and percent blank."
                )
            if not buy_quantity or not get_quantity:
                raise serializers.ValidationError(
                    "Buy X Get Y requires both buy quantity and get quantity."
                )
            if fixed_quantity or fixed_bundle_amount:
                raise serializers.ValidationError(
                    "Fixed-set fields are only valid for X for fixed amount offers."
                )
        elif offer_type == Promotion.OfferType.X_FOR_FIXED_AMOUNT:
            if has_pct or has_amt:
                raise serializers.ValidationError(
                    "X for fixed amount uses set quantity and set price; leave amount and percent blank."
                )
            if not fixed_quantity or fixed_bundle_amount is None:
                raise serializers.ValidationError(
                    "X for fixed amount requires both set quantity and set price."
                )
            if buy_quantity or get_quantity:
                raise serializers.ValidationError(
                    "Buy/get quantities are only valid for Buy X Get Y offers."
                )
        else:
            if has_pct == has_amt:
                raise serializers.ValidationError(
                    "Set exactly one of discount_percent or discount_amount."
                )
            if buy_quantity or get_quantity or fixed_quantity or fixed_bundle_amount or max_uses_per_order:
                raise serializers.ValidationError(
                    "Quantity-deal fields are only valid for Buy X Get Y or X for fixed amount offers."
                )

        tenant = self.context["request"].tenant
        menu_item = attrs.get("menu_item", inst.menu_item if inst else None)
        product_family = attrs.get("product_family", inst.product_family if inst else None)
        category = attrs.get("category", inst.category if inst else None)
        brand = (attrs.get("brand", inst.brand if inst else "") or "").strip()
        reward_menu_item = attrs.get("reward_menu_item", inst.reward_menu_item if inst else None)
        reward_product_family = attrs.get(
            "reward_product_family",
            inst.reward_product_family if inst else None,
        )
        reward_category = attrs.get("reward_category", inst.reward_category if inst else None)
        reward_brand = (
            attrs.get("reward_brand", inst.reward_brand if inst else "") or ""
        ).strip()
        if sum(bool(value) for value in (menu_item, product_family, category, brand)) > 1:
            raise serializers.ValidationError(
                "Choose only one promotion target: product, product family, category, or brand."
            )
        if (
            offer_type in {
                Promotion.OfferType.BUY_X_GET_Y,
                Promotion.OfferType.X_FOR_FIXED_AMOUNT,
            }
            and sum(bool(value) for value in (menu_item, product_family, category, brand)) != 1
        ):
            raise serializers.ValidationError(
                "Quantity deals require exactly one product, product family, category, or brand target."
            )
        if menu_item is not None and menu_item.tenant_id != tenant.pk:
            raise serializers.ValidationError({"menu_item": "Choose a product from this business."})
        reward_targets = (reward_menu_item, reward_product_family, reward_category, reward_brand)
        if sum(bool(value) for value in reward_targets) > 1:
            raise serializers.ValidationError(
                "Choose only one Buy X Get Y reward target: product, product family, category, or brand."
            )
        if offer_type != Promotion.OfferType.BUY_X_GET_Y and any(reward_targets):
            raise serializers.ValidationError(
                "Reward targets are only valid for Buy X Get Y offers."
            )
        if reward_menu_item is not None and reward_menu_item.tenant_id != tenant.pk:
            raise serializers.ValidationError({"reward_menu_item": "Choose a reward product from this business."})
        if reward_product_family is not None and reward_product_family.tenant_id != tenant.pk:
            raise serializers.ValidationError({"reward_product_family": "Choose a reward family from this business."})
        if reward_category is not None and reward_category.tenant_id != tenant.pk:
            raise serializers.ValidationError({"reward_category": "Choose a reward category from this business."})
        if product_family is not None and product_family.tenant_id != tenant.pk:
            raise serializers.ValidationError({"product_family": "Choose a product family from this business."})
        if category is not None and category.tenant_id != tenant.pk:
            raise serializers.ValidationError({"category": "Choose a category from this business."})
        attrs["brand"] = brand
        attrs["reward_brand"] = reward_brand

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

        weekdays = attrs.get(
            "schedule_weekdays",
            inst.schedule_weekdays if inst else [],
        ) or []
        try:
            normalized_weekdays = sorted({int(value) for value in weekdays})
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({
                "schedule_weekdays": "Weekdays must be numbers from 1 to 7."
            }) from exc
        if any(day < 1 or day > 7 for day in normalized_weekdays):
            raise serializers.ValidationError({
                "schedule_weekdays": "Weekdays must be numbers from 1 to 7."
            })
        attrs["schedule_weekdays"] = normalized_weekdays
        schedule_start = attrs.get(
            "schedule_start_time",
            inst.schedule_start_time if inst else None,
        )
        schedule_end = attrs.get(
            "schedule_end_time",
            inst.schedule_end_time if inst else None,
        )
        if (schedule_start is None) != (schedule_end is None):
            raise serializers.ValidationError(
                "Set both recurring start and end times, or leave both blank."
            )
        if schedule_start is not None and schedule_end <= schedule_start:
            raise serializers.ValidationError({
                "schedule_end_time": (
                    "Recurring end time must be later than start time. "
                    "Split overnight offers into two schedules."
                )
            })
        starts_at = attrs.get("starts_at", inst.starts_at if inst else None)
        ends_at = attrs.get("ends_at", inst.ends_at if inst else None)
        if starts_at is not None and ends_at is not None and ends_at <= starts_at:
            raise serializers.ValidationError({
                "ends_at": "Offer end must be later than its start."
            })

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
