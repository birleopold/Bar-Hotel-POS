from django.contrib import admin

from .models import CashbookEntry, FinanceCategory


@admin.register(FinanceCategory)
class FinanceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "tenant", "is_active", "sort_order")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "tenant__name")


@admin.register(CashbookEntry)
class CashbookEntryAdmin(admin.ModelAdmin):
    list_display = ("transaction_date", "category", "amount", "tenant", "site", "created_by")
    list_filter = ("transaction_date",)
    search_fields = ("note", "reference", "tenant__name")
    raw_id_fields = ("category", "site", "created_by")
