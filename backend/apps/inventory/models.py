import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import TimeStampedModel


class StockReason(models.TextChoices):
    RECEIVE = "receive", "Receive / purchase"
    SALE = "sale", "Sale (POS)"
    ADJUST_IN = "adjust_in", "Adjustment increase"
    ADJUST_OUT = "adjust_out", "Adjustment decrease"
    WASTE = "waste", "Waste / shrink"
    TRANSFER_OUT = "transfer_out", "Transfer out"
    TRANSFER_IN = "transfer_in", "Transfer in"
    PHYSICAL_COUNT = "physical_count", "Physical count adjustment"
    RECIPE = "recipe", "Recipe / BOM consumption"


class StockBalance(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="stock_balances",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="stock_balances",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.CASCADE,
        related_name="stock_balances",
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        unique_together = [["outlet", "menu_item"]]
        ordering = ["outlet", "menu_item__name"]

    def __str__(self) -> str:
        return f"{self.outlet}:{self.menu_item.name}={self.quantity}"


class StockMovement(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    quantity_change = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        help_text="Positive adds stock; negative removes (e.g. sale).",
    )
    reason = models.CharField(max_length=16, choices=StockReason.choices)
    order = models.ForeignKey(
        "pos.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    note = models.CharField(max_length=512, blank=True)
    purchase_order = models.ForeignKey(
        "purchasing.PurchaseOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    transfer_batch = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Links paired transfer_out / transfer_in rows.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.reason} {self.quantity_change} {self.menu_item.name}"


class StockCountStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class StockCountSession(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="stock_count_sessions",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="stock_count_sessions",
    )
    status = models.CharField(
        max_length=16,
        choices=StockCountStatus.choices,
        default=StockCountStatus.DRAFT,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_count_sessions",
    )
    note = models.CharField(max_length=512, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Count {self.outlet} ({self.status})"


class StockCountLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        StockCountSession,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.CASCADE,
        related_name="stock_count_lines",
    )
    counted_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    system_quantity_before = models.DecimalField(max_digits=14, decimal_places=3)
    variance = models.DecimalField(max_digits=14, decimal_places=3)

    class Meta:
        ordering = ["menu_item__name"]
        unique_together = [["session", "menu_item"]]

    def __str__(self) -> str:
        return f"{self.menu_item.name}: {self.counted_quantity}"
