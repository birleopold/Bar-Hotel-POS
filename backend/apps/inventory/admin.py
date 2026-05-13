from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import StockBalance, StockCountLine, StockCountSession, StockMovement


class StockCountLineInline(admin.TabularInline):
    model = StockCountLine
    extra = 0
    readonly_fields = ("counted_quantity", "system_quantity_before", "variance")


@admin.register(StockCountSession)
class StockCountSessionAdmin(PlatformOperatorModelAdmin):
    list_display = ("outlet", "status", "created_by", "completed_at", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("note",)
    inlines = [StockCountLineInline]
    autocomplete_fields = ("outlet", "created_by")


@admin.register(StockBalance)
class StockBalanceAdmin(PlatformOperatorModelAdmin):
    list_display = ("menu_item", "outlet", "quantity", "tenant")
    list_filter = ("tenant", "outlet")
    search_fields = ("menu_item__name", "menu_item__barcode", "menu_item__sku")
    autocomplete_fields = ("outlet", "menu_item")


@admin.register(StockMovement)
class StockMovementAdmin(PlatformOperatorModelAdmin):
    list_display = ("created_at", "reason", "quantity_change", "menu_item", "outlet", "order")
    list_filter = ("reason", "tenant")
    search_fields = ("note", "menu_item__name")
    readonly_fields = ("id", "tenant", "outlet", "menu_item", "quantity_change", "reason", "order", "created_by", "note", "created_at", "updated_at")
    autocomplete_fields = ("outlet", "menu_item", "order", "created_by")
