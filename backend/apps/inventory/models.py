import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

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
    ASSEMBLY_BUILD = "assembly_build", "Assembly build"
    ASSEMBLY_UNBUILD = "assembly_unbuild", "Assembly unbuild"


class RetailAssemblyRun(TimeStampedModel):
    class Direction(models.TextChoices):
        BUILD = "build", "Build"
        UNBUILD = "unbuild", "Unbuild"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="retail_assembly_runs",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.PROTECT,
        related_name="retail_assembly_runs",
    )
    assembled_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.PROTECT,
        related_name="retail_assembly_runs",
    )
    direction = models.CharField(max_length=16, choices=Direction.choices)
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    note = models.CharField(max_length=512, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retail_assembly_runs_created",
    )

    class Meta:
        ordering = ["-created_at"]


class SerializedUnitStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    RESERVED = "reserved", "Reserved for basket"
    SOLD = "sold", "Sold"
    RETURNED = "returned", "Returned to stock"
    QUARANTINED = "quarantined", "Quarantined"
    RETIRED = "retired", "Retired / written off"


class SerializedUnitEventType(models.TextChoices):
    RECEIVED = "received", "Received"
    RESERVED = "reserved", "Reserved"
    RELEASED = "released", "Released"
    SOLD = "sold", "Sold"
    RETURNED = "returned", "Returned"
    TRANSFERRED = "transferred", "Transferred"
    QUARANTINED = "quarantined", "Quarantined"
    RETIRED = "retired", "Retired"


class InventorySerialUnit(TimeStampedModel):
    """One physical serialized/IMEI-tracked retail unit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="serialized_units",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.PROTECT,
        related_name="serialized_units",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.PROTECT,
        related_name="serialized_units",
    )
    serial_number = models.CharField(max_length=128)
    secondary_identifier = models.CharField(
        max_length=128,
        blank=True,
        help_text="Optional secondary identifier such as IMEI2 or manufacturer serial.",
    )
    status = models.CharField(
        max_length=16,
        choices=SerializedUnitStatus.choices,
        default=SerializedUnitStatus.AVAILABLE,
    )
    purchase_receipt_line = models.ForeignKey(
        "purchasing.PurchaseReceiptLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="serialized_units",
    )
    reserved_order_line = models.ForeignKey(
        "pos.OrderLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reserved_serial_units",
    )
    sold_order_line = models.ForeignKey(
        "pos.OrderLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sold_serial_units",
    )
    received_at = models.DateField()
    sold_at = models.DateTimeField(null=True, blank=True)
    warranty_started_at = models.DateField(null=True, blank=True)
    warranty_expires_at = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["menu_item__name", "serial_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "serial_number"],
                name="uniq_tenant_serial_number",
            ),
            models.UniqueConstraint(
                Lower("serial_number"),
                "tenant",
                name="uniq_tenant_serial_number_ci",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "outlet", "status"],
                name="serial_outlet_status_idx",
            ),
            models.Index(
                fields=["tenant", "menu_item", "status"],
                name="serial_item_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.menu_item.name} · {self.serial_number}"


class InventorySerialEvent(TimeStampedModel):
    """Immutable trace event for serialized stock custody and sale lifecycle."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="serialized_unit_events",
    )
    serial_unit = models.ForeignKey(
        InventorySerialUnit,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=16, choices=SerializedUnitEventType.choices)
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.PROTECT,
        related_name="serialized_unit_events",
    )
    order_line = models.ForeignKey(
        "pos.OrderLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="serialized_unit_events",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="serialized_unit_events_created",
    )
    note = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["-created_at"]


class InventorySerialReturnLink(TimeStampedModel):
    """Bind exact serialized units to an existing retail return record."""

    class Disposition(models.TextChoices):
        RESTOCKED = "restocked", "Returned to saleable stock"
        QUARANTINED = "quarantined", "Returned but quarantined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="serialized_return_links",
    )
    serial_unit = models.ForeignKey(
        InventorySerialUnit,
        on_delete=models.PROTECT,
        related_name="return_links",
    )
    return_record = models.ForeignKey(
        "pos.SupermarketLineReturn",
        on_delete=models.CASCADE,
        related_name="serialized_unit_links",
    )
    disposition = models.CharField(max_length=16, choices=Disposition.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["serial_unit", "return_record"],
                name="uniq_serial_unit_return_record",
            ),
        ]


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
    assembly_run = models.ForeignKey(
        RetailAssemblyRun,
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
    """Legacy instant checks plus individually tracked staged transfers."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="transfer_receipts")
    transfer_batch = models.UUIDField(unique=True)
    from_outlet = models.ForeignKey("tenants.Outlet", on_delete=models.PROTECT, related_name="sent_transfer_receipts")
    to_outlet = models.ForeignKey("tenants.Outlet", on_delete=models.PROTECT, related_name="received_transfer_receipts")
    menu_item = models.ForeignKey("catalog.MenuItem", on_delete=models.PROTECT, related_name="transfer_receipts")
    dispatched_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    mode = models.CharField(max_length=12, default="instant", choices=[
        ("instant", "Legacy immediate"), ("staged", "Dispatch then receive"),
    ])
    posted_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    returned_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    written_off_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    received_quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    status = models.CharField(max_length=16, default="awaiting", choices=[
        ("awaiting", "Awaiting check"), ("in_transit", "In transit"),
        ("matched", "Matched"), ("disputed", "Discrepancy"), ("resolved", "Resolved"),
    ])
    dispatched_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="transfer_dispatches")
    checked_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="transfer_checks")
    checked_at = models.DateTimeField(null=True, blank=True)
    discrepancy_note = models.CharField(max_length=512, blank=True)
    resolution_action = models.CharField(max_length=24, blank=True)
    resolution_note = models.CharField(max_length=512, blank=True)
    resolved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="resolved_stock_transfers")
    resolved_at = models.DateTimeField(null=True, blank=True)

    @property
    def outstanding_quantity(self):
        if self.mode != "staged":
            return Decimal("0")
        return self.dispatched_quantity - self.posted_quantity - self.returned_quantity - self.written_off_quantity
    review_action = models.CharField(max_length=20, blank=True, default="", choices=[
        ("", "Not reviewed"),
        ("needs_count", "Physical recount required"),
        ("documented", "Investigation documented"),
    ])
    review_note = models.CharField(max_length=512, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_transfer_discrepancies",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(dispatched_quantity__gt=0), name="transfer_receipt_dispatched_positive"),
            models.CheckConstraint(condition=models.Q(received_quantity__gte=0) | models.Q(received_quantity__isnull=True), name="transfer_receipt_received_nonnegative"),
            models.CheckConstraint(condition=models.Q(posted_quantity__gte=0), name="transfer_posted_nonnegative"),
            models.CheckConstraint(condition=models.Q(returned_quantity__gte=0), name="transfer_returned_nonnegative"),
            models.CheckConstraint(condition=models.Q(written_off_quantity__gte=0), name="transfer_writtenoff_nonnegative"),
            models.CheckConstraint(condition=models.Q(dispatched_quantity__gte=models.F("posted_quantity") + models.F("returned_quantity") + models.F("written_off_quantity")), name="transfer_total_not_exceeded"),
        ]

class StockShelfLocation(TimeStampedModel):
    """Physical picking address for a product in an outlet; not a stock balance."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="stock_shelf_locations")
    outlet = models.ForeignKey("tenants.Outlet", on_delete=models.CASCADE, related_name="shelf_locations")
    menu_item = models.ForeignKey("catalog.MenuItem", on_delete=models.CASCADE, related_name="shelf_locations")
    aisle = models.CharField(max_length=32, blank=True)
    shelf = models.CharField(max_length=32, blank=True)
    bin_code = models.CharField(max_length=32, blank=True)
    note = models.CharField(max_length=160, blank=True)
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="shelf_locations_updated")

    class Meta:
        ordering = ["outlet__name", "menu_item__name"]
        constraints = [
            models.UniqueConstraint(fields=["outlet", "menu_item"], name="uniq_shelf_location_outlet_product"),
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
