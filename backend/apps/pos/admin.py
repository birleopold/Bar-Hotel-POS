from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import (
    OfflineQueuedOperation,
    Order,
    OrderLine,
    Payment,
    PosShift,
    Refund,
    SupermarketLineReturn,
    Table,
)


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ("line_total", "tax_amount", "kds_station", "kds_status")


@admin.register(Table)
class TableAdmin(PlatformOperatorModelAdmin):
    list_display = ("label", "outlet", "capacity", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("label",)
    autocomplete_fields = ("outlet",)


@admin.register(Payment)
class PaymentAdmin(PlatformOperatorModelAdmin):
    list_display = ("amount", "method", "order", "tenant", "created_at")
    list_filter = ("method", "tenant")
    search_fields = ("idempotency_key", "order__bill_reference")
    readonly_fields = ("id", "tenant", "order", "amount", "method", "idempotency_key", "recorded_by", "created_at", "updated_at")


@admin.register(Refund)
class RefundAdmin(PlatformOperatorModelAdmin):
    list_display = ("amount", "order", "tenant", "restocked", "created_at")
    list_filter = ("tenant", "restocked")
    search_fields = ("order__bill_reference", "idempotency_key")
    readonly_fields = (
        "id",
        "tenant",
        "order",
        "payment",
        "amount",
        "reason",
        "idempotency_key",
        "recorded_by",
        "restocked",
        "created_at",
        "updated_at",
    )


@admin.register(OfflineQueuedOperation)
class OfflineQueuedOperationAdmin(PlatformOperatorModelAdmin):
    list_display = ("client_mutation_id", "operation_type", "status", "tenant", "outlet", "created_at")
    list_filter = ("status", "operation_type", "tenant")
    search_fields = ("client_mutation_id",)
    readonly_fields = (
        "id",
        "tenant",
        "outlet",
        "client_mutation_id",
        "operation_type",
        "payload",
        "status",
        "error_message",
        "applied_payment_id",
        "applied_order_id",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("tenant", "outlet")


@admin.register(Order)
class OrderAdmin(PlatformOperatorModelAdmin):
    list_display = (
        "bill_reference",
        "outlet",
        "table",
        "status",
        "discount_amount",
        "total",
        "is_paid",
        "created_at",
    )
    list_filter = ("status", "is_paid", "tenant")
    search_fields = ("bill_reference", "table_label")
    inlines = [OrderLineInline]
    autocomplete_fields = ("outlet", "created_by", "table", "folio", "applied_promotion")


@admin.register(PosShift)
class PosShiftAdmin(PlatformOperatorModelAdmin):
    list_display = ("outlet", "status", "opening_cash", "expected_cash", "counted_cash", "opened_at", "closed_at")
    list_filter = ("status", "tenant", "outlet")
    autocomplete_fields = ("tenant", "outlet", "opened_by", "closed_by")


@admin.register(SupermarketLineReturn)
class SupermarketLineReturnAdmin(PlatformOperatorModelAdmin):
    list_display = ("order", "order_line", "quantity", "restocked", "created_at")
    list_filter = ("tenant", "restocked")
    search_fields = ("order__bill_reference", "order_line__label", "reason")
    autocomplete_fields = ("tenant", "order", "created_by")
