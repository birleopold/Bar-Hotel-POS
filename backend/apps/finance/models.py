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
    PURCHASE_RECEIVE_MOVEMENT = "purchase_receive_movement", "Purchase receive movement"


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
