from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import (
    BillingEvent,
    BillingInvoice,
    Outlet,
    Plan,
    Site,
    Tenant,
    TenantFeatureEntitlement,
    TenantOutletModulePolicy,
    TenantSettings,
    TenantSubscription,
)


class TenantSettingsInline(admin.StackedInline):
    model = TenantSettings
    can_delete = False
    fields = (
        "default_currency",
        "default_timezone",
        "receipt_footer",
        "theme_primary",
        "theme_secondary",
        "theme_accent",
        "logo_url",
        "enabled_staff_modules",
        "hardware_barcode_scanner_enabled",
        "hardware_cash_drawer_enabled",
        "hardware_receipt_printer_enabled",
    )


@admin.register(Tenant)
class TenantAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TenantSettingsInline]


@admin.register(Site)
class SiteAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "tenant", "city", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "city")


@admin.register(Outlet)
class OutletAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "site", "outlet_type", "is_active")
    list_filter = ("outlet_type", "is_active")
    search_fields = ("name", "site__name")


@admin.register(Plan)
class PlanAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "code", "monthly_price", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(PlatformOperatorModelAdmin):
    list_display = ("tenant", "plan", "status", "current_period_ends_at")
    list_filter = ("status", "plan")
    search_fields = ("tenant__name", "plan__name")


@admin.register(TenantFeatureEntitlement)
class TenantFeatureEntitlementAdmin(PlatformOperatorModelAdmin):
    list_display = ("tenant", "module_key", "is_enabled")
    list_filter = ("module_key", "is_enabled")
    search_fields = ("tenant__name", "module_key")


@admin.register(TenantOutletModulePolicy)
class TenantOutletModulePolicyAdmin(PlatformOperatorModelAdmin):
    list_display = ("tenant", "outlet_type", "is_active")
    list_filter = ("outlet_type", "is_active")
    search_fields = ("tenant__name", "outlet_type")


@admin.register(BillingInvoice)
class BillingInvoiceAdmin(PlatformOperatorModelAdmin):
    list_display = ("tenant", "invoice_number", "amount", "currency", "status", "due_at", "paid_at")
    list_filter = ("status", "currency")
    search_fields = ("tenant__name", "invoice_number", "external_ref")


@admin.register(BillingEvent)
class BillingEventAdmin(PlatformOperatorModelAdmin):
    list_display = ("tenant", "event_type", "occurred_at", "actor", "invoice", "subscription")
    list_filter = ("event_type",)
    search_fields = ("tenant__name", "message")
