from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import (
    MenuCategory,
    MenuItem,
    MenuItemOutlet,
    MenuItemRecipeLine,
    Promotion,
    ServiceOffering,
    ServiceOfferingOption,
    SupermarketSkuProfile,
)


class MenuItemOutletInline(admin.TabularInline):
    model = MenuItemOutlet
    extra = 0
    autocomplete_fields = ("outlet",)


class MenuItemRecipeLineInline(admin.TabularInline):
    model = MenuItemRecipeLine
    fk_name = "parent_item"
    extra = 0
    autocomplete_fields = ("ingredient_item",)


class ServiceOfferingOptionInline(admin.TabularInline):
    model = ServiceOfferingOption
    extra = 0
    fields = ("name", "price", "duration_minutes", "kds_station", "sort_order", "is_active")


@admin.register(Promotion)
class PromotionAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "tenant", "starts_at", "ends_at", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)
    autocomplete_fields = ("tenant",)
    filter_horizontal = ("outlets",)


@admin.register(MenuCategory)
class MenuCategoryAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "tenant", "sort_order", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)


@admin.register(MenuItem)
class MenuItemAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "category", "unit_price", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "sku", "barcode")
    autocomplete_fields = ("category",)
    inlines = [MenuItemOutletInline, MenuItemRecipeLineInline]


@admin.register(SupermarketSkuProfile)
class SupermarketSkuProfileAdmin(PlatformOperatorModelAdmin):
    list_display = ("menu_item", "tenant", "department", "barcode_mode", "weighted_pricing_mode", "is_active")
    list_filter = ("tenant", "barcode_mode", "weighted_pricing_mode", "is_active")
    search_fields = ("menu_item__name", "plu_code")
    autocomplete_fields = ("menu_item", "tenant")


@admin.register(ServiceOffering)
class ServiceOfferingAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "tenant", "default_price", "kds_station", "is_active")
    list_filter = ("tenant", "is_active", "kds_station")
    search_fields = ("name", "description")
    autocomplete_fields = ("tenant", "outlets")
    filter_horizontal = ("outlets",)
    inlines = [ServiceOfferingOptionInline]
