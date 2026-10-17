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
    REVIEW = "review", "Awaiting approval"
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
    submitted_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="submitted_stock_counts")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_stock_counts")
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



class StockTransferReceipt(TimeStampedModel):
    """Destination verification of an already-posted internal stock transfer.

    This is NOT an in-transit inventory balance or a second ledger.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="transfer_receipts")
    transfer_batch = models.UUIDField(unique=True)
    from_outlet = models.ForeignKey("tenants.Outlet", on_delete=models.PROTECT, related_name="sent_transfer_receipts")
    to_outlet = models.ForeignKey("tenants.Outlet", on_delete=models.PROTECT, related_name="received_transfer_receipts")
    menu_item = models.ForeignKey("catalog.MenuItem", on_delete=models.PROTECT, related_name="transfer_receipts")
    dispatched_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    received_quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    status = models.CharField(max_length=16, default="awaiting", choices=[
        ("awaiting", "Awaiting check"), ("matched", "Matched"), ("disputed", "Discrepancy"),
    ])
    dispatched_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="transfer_dispatches")
    checked_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="transfer_checks")
    checked_at = models.DateTimeField(null=True, blank=True)
    discrepancy_note = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(dispatched_quantity__gt=0), name="transfer_receipt_dispatched_positive"),
            models.CheckConstraint(condition=models.Q(received_quantity__gte=0) | models.Q(received_quantity__isnull=True), name="transfer_receipt_received_nonnegative"),
        ]

# Batch model imported here so Django registers it with the inventory app.
from .batches import InventoryBatch  # noqa: E402,F401


class StockBatchAllocation(TimeStampedModel):
    """Permanent movement-to-batch traceability for sale, waste and transfers."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="stock_batch_allocations",
    )
    stock_movement = models.ForeignKey(
        StockMovement, on_delete=models.PROTECT, related_name="batch_allocations",
    )
    batch = models.ForeignKey(
        "inventory.InventoryBatch", on_delete=models.PROTECT, related_name="movement_allocations",
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["stock_movement", "batch"], name="uniq_stock_movement_batch_link",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="stock_batch_allocation_positive",
            ),
        ]
