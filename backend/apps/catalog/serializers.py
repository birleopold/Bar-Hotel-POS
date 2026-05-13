from drf_spectacular.utils import extend_schema_field
from django.db.models import Prefetch
from rest_framework import serializers

from apps.tenants.models import Outlet

from .models import MenuCategory, MenuItem, MenuItemModifierGroup, MenuItemOutlet, ModifierGroup, ModifierOption


class MenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = [
            "id",
            "name",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MenuItemOutletLinkSerializer(serializers.ModelSerializer):
    outlet_id = serializers.UUIDField(source="outlet.id", read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)

    class Meta:
        model = MenuItemOutlet
        fields = ["outlet_id", "outlet_name", "price_override"]


class MenuItemSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=MenuCategory.objects.none())
    category_id = serializers.UUIDField(source="category.id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    outlet_links = MenuItemOutletLinkSerializer(many=True, read_only=True)
    outlet_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        help_text="If provided, item is limited to these outlets; omit for all outlets.",
    )
    modifier_groups = serializers.SerializerMethodField(read_only=True)
    modifier_group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        help_text="Ordered list of modifier group ids attached to this item.",
    )

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "category",
            "category_id",
            "category_name",
            "name",
            "description",
            "sku",
            "barcode",
            "unit_of_measure",
            "track_inventory",
            "reorder_level",
            "kds_station",
            "consume_recipe_on_sale",
            "unit_price",
            "tax_rate_percent",
            "is_active",
            "outlet_links",
            "outlet_ids",
            "modifier_groups",
            "modifier_group_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "category_id",
            "category_name",
            "outlet_links",
            "modifier_groups",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(
        {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "name": {"type": "string"},
                    "min_selections": {"type": "integer"},
                    "max_selections": {"type": "integer", "nullable": True},
                    "options": {"type": "array"},
                },
            },
        }
    )
    def get_modifier_groups(self, obj: MenuItem) -> list:
        links = (
            MenuItemModifierGroup.objects.filter(menu_item=obj)
            .select_related("group")
            .prefetch_related(
                Prefetch(
                    "group__options",
                    queryset=ModifierOption.objects.filter(is_active=True).order_by(
                        "sort_order", "name"
                    ),
                )
            )
            .order_by("sort_order", "group__name")
        )
        out = []
        for link in links:
            g = link.group
            out.append(
                {
                    "id": str(g.id),
                    "name": g.name,
                    "min_selections": g.min_selections,
                    "max_selections": g.max_selections,
                    "options": [
                        {
                            "id": str(o.id),
                            "name": o.name,
                            "price_delta": str(o.price_delta),
                            "sort_order": o.sort_order,
                        }
                        for o in g.options.all()
                    ],
                }
            )
        return out

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["category"].queryset = MenuCategory.objects.filter(tenant=tenant)

    def validate_category(self, value: MenuCategory) -> MenuCategory:
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Category must belong to the current tenant.")
        return value

    def create(self, validated_data):
        outlet_ids = validated_data.pop("outlet_ids", None)
        mod_group_ids = validated_data.pop("modifier_group_ids", serializers.empty)
        item = super().create(validated_data)
        self._sync_outlets(item, outlet_ids)
        if mod_group_ids is not serializers.empty:
            self._sync_modifier_groups(item, mod_group_ids)
        return item

    def update(self, instance, validated_data):
        outlet_ids = validated_data.pop("outlet_ids", serializers.empty)
        mod_group_ids = validated_data.pop("modifier_group_ids", serializers.empty)
        item = super().update(instance, validated_data)
        if outlet_ids is not serializers.empty:
            self._sync_outlets(item, outlet_ids)
        if mod_group_ids is not serializers.empty:
            self._sync_modifier_groups(item, mod_group_ids)
        return item

    def _sync_outlets(self, item: MenuItem, outlet_ids: list | None) -> None:
        if outlet_ids is None:
            return
        tenant_id = item.tenant_id
        outlets = list(Outlet.objects.filter(id__in=outlet_ids, site__tenant_id=tenant_id))
        if len(outlets) != len(set(outlet_ids)):
            raise serializers.ValidationError({"outlet_ids": "One or more outlets are invalid for this tenant."})
        item.outlets.clear()
        for o in outlets:
            MenuItemOutlet.objects.get_or_create(menu_item=item, outlet=o)

    def _sync_modifier_groups(self, item: MenuItem, group_ids: list) -> None:
        tenant_id = item.tenant_id
        groups = list(ModifierGroup.objects.filter(id__in=group_ids, tenant_id=tenant_id))
        if len(groups) != len(set(group_ids)):
            raise serializers.ValidationError(
                {"modifier_group_ids": "One or more modifier groups are invalid for this tenant."}
            )
        MenuItemModifierGroup.objects.filter(menu_item=item).delete()
        order_map = {str(gid): i for i, gid in enumerate(group_ids)}
        for g in groups:
            MenuItemModifierGroup.objects.create(
                menu_item=item, group=g, sort_order=order_map[str(g.id)]
            )


class MenuItemListSerializer(serializers.ModelSerializer):
    """Lighter list for POS; includes effective price when ``context[outlet_id]`` is set."""

    category_id = serializers.UUIDField(source="category.id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    effective_unit_price = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "category_id",
            "category_name",
            "name",
            "description",
            "sku",
            "unit_price",
            "effective_unit_price",
            "barcode",
            "unit_of_measure",
            "track_inventory",
            "kds_station",
            "consume_recipe_on_sale",
            "tax_rate_percent",
            "is_active",
        ]

    @extend_schema_field(serializers.CharField(help_text="Decimal string; outlet-specific when context has outlet_id."))
    def get_effective_unit_price(self, obj: MenuItem):
        oid = self.context.get("outlet_id")
        if oid is not None:
            return str(obj.unit_price_for_outlet(oid))
        return str(obj.unit_price)
