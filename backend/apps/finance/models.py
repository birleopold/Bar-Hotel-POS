from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import TimeStampedModel


class FinanceCategoryKind(models.TextChoices):
    INCOME = "income", "Income"
    EXPENSE = "expense", "Expense"


class FinanceCategory(TimeStampedModel):
    """User-defined income / expense bucket for manual cashbook lines (non-POS)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="finance_categories",
    )
    name = models.CharField(max_length=128)
    kind = models.CharField(max_length=16, choices=FinanceCategoryKind.choices)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "sort_order", "name"]
        unique_together = [["tenant", "name", "kind"]]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.name}"


class CashbookEntry(TimeStampedModel):
    """Manual cashbook line (income or expense per category)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="cashbook_entries",
    )
    category = models.ForeignKey(
        FinanceCategory,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    site = models.ForeignKey(
        "tenants.Site",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cashbook_entries",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    transaction_date = models.DateField(db_index=True)
    reference = models.CharField(max_length=64, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cashbook_entries",
    )

    class Meta:
        ordering = ["-transaction_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.transaction_date} {self.category} {self.amount}"


class FinancePostingSource(models.TextChoices):
    POS_PAYMENT = "pos_payment", "POS payment"
    POS_REFUND = "pos_refund", "POS refund"
    FOLIO_PAYMENT = "folio_payment", "Folio payment"
    PURCHASE_RECEIVE_MOVEMENT = "purchase_receive_movement", "Purchase receive movement"
    SUPPLIER_PAYMENT = "supplier_payment", "Supplier payment"
    EVENT_PAYMENT = "event_payment", "Event payment"


class FinancePostingLink(TimeStampedModel):
    """
    Idempotency bridge between operational events and cashbook entries.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="finance_posting_links",
    )
    source_type = models.CharField(max_length=48, choices=FinancePostingSource.choices)
    source_id = models.CharField(max_length=64)
    cashbook_entry = models.OneToOneField(
        CashbookEntry,
        on_delete=models.CASCADE,
        related_name="posting_link",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_type", "source_id"],
                name="uniq_finance_posting_source_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_type}:{self.source_id}"


class AccountingMappingKind(models.TextChoices):
    REVENUE_DEFAULT = "revenue_default", "Revenue default"
    REVENUE_CATEGORY = "revenue_category", "Revenue category"
    RETURNS = "returns", "Sales returns"
    TENDER = "tender", "Tender clearing"
    TAX_LIABILITY = "tax_liability", "Tax / VAT liability"
    ACCOUNTS_RECEIVABLE = "accounts_receivable", "Accounts receivable"
    ACCOUNTS_PAYABLE = "accounts_payable", "Accounts payable"
    INVENTORY_DEFAULT = "inventory_default", "Inventory asset default"
    INVENTORY_CATEGORY = "inventory_category", "Inventory asset category"
    COGS_DEFAULT = "cogs_default", "COGS default"
    COGS_CATEGORY = "cogs_category", "COGS category"


class AccountingMapping(TimeStampedModel):
    """Provider-neutral accounting account mapping for operational exports."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="accounting_mappings",
    )
    kind = models.CharField(max_length=32, choices=AccountingMappingKind.choices)
    source_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Category UUID, tender method, or blank for a default mapping.",
    )
    source_label = models.CharField(max_length=128, blank=True, default="")
    account_code = models.CharField(max_length=64)
    account_name = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounting_mappings_created",
    )

    class Meta:
        ordering = ["kind", "source_label", "account_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "kind", "source_key"],
                name="uniq_accounting_mapping_source_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.account_code} {self.account_name}"


class AccountingExportBatch(TimeStampedModel):
    """Immutable journal export snapshot for replay/download and audit evidence."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="accounting_export_batches",
    )
    date_from = models.DateField()
    date_to = models.DateField()
    currency = models.CharField(max_length=3)
    scope_outlet_ids = models.JSONField(default=list, blank=True)
    mapping_snapshot = models.JSONField(default=dict, blank=True)
    journal_lines = models.JSONField(default=list, blank=True)
    source_summary = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=64, db_index=True)
    line_count = models.PositiveIntegerField(default=0)
    total_debit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    total_credit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounting_exports_generated",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "fingerprint"],
                name="uniq_accounting_export_fingerprint_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date_from}–{self.date_to} {self.currency} ({self.line_count} lines)"
