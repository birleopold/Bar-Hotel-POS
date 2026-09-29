from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine, Supplier


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


class PurchaseReceiptLineInline(admin.TabularInline):
    model = PurchaseReceiptLine
    extra = 0


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "is_active", "created_at")
    list_filter = ("tenant", "is_active")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(PlatformOperatorModelAdmin):
    list_display = ("reference", "supplier", "outlet", "status", "tenant", "created_at")
    list_filter = ("tenant", "status")
    inlines = [PurchaseOrderLineInline]


@admin.register(PurchaseReceipt)
class PurchaseReceiptAdmin(PlatformOperatorModelAdmin):
    list_display = ("delivery_reference", "purchase_order", "received_by", "created_at", "tenant")
    list_filter = ("tenant", "created_at")
    search_fields = ("delivery_reference", "note", "purchase_order__reference")
    inlines = [PurchaseReceiptLineInline]
