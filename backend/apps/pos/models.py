import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import TimeStampedModel


class Table(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="tables",
    )
    label = models.CharField(max_length=64)
    capacity = models.PositiveSmallIntegerField(default=4, validators=[MinValueValidator(1)])
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["outlet", "sort_order", "label"]
        unique_together = [["outlet", "label"]]

    def __str__(self) -> str:
        return f"{self.outlet}:{self.label}"


class OrderStatus(models.TextChoices):
    OPEN = "open", "Open"
    CANCELLED = "cancelled", "Cancelled"
    CLOSED = "closed", "Closed"


class Order(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    table = models.ForeignKey(
        Table,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    status = models.CharField(
        max_length=16,
        choices=OrderStatus.choices,
        default=OrderStatus.OPEN,
    )
    bill_reference = models.CharField(max_length=32, blank=True, default="", db_index=True)
    table_label = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_created",
    )
    currency = models.CharField(max_length=3, default="USD")
    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    tax_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Order-level discount subtracted after line subtotals and tax (open orders only).",
    )
    folio = models.ForeignKey(
        "lodging.Folio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    applied_promotion = models.ForeignKey(
        "catalog.Promotion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "bill_reference"],
                name="uniq_order_bill_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bill_reference} ({self.status})"

    def save(self, *args, **kwargs) -> None:
        if self._state.adding and not self.bill_reference:
            self.bill_reference = f"B-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class KdsLineStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PREP = "in_prep", "In prep"
    READY = "ready", "Ready"
    SERVED = "served", "Served"


class OrderLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_lines",
    )
    label = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Line subtotal before tax (qty × unit price).",
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    line_discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    line_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    pricing_source = models.CharField(
        max_length=24,
        default="menu",
        help_text="Price source marker (menu, barcode, plu, weighted, manual).",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_voided = models.BooleanField(default=False)
    void_reason = models.CharField(max_length=255, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_lines_voided",
    )
    kds_station = models.CharField(max_length=32, blank=True)
    kds_status = models.CharField(
        max_length=16,
        choices=KdsLineStatus.choices,
        default=KdsLineStatus.PENDING,
    )
    modifiers_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="Chosen modifier options at sale time (name + price_delta per option).",
    )

    class Meta:
        ordering = ["order", "sort_order", "created_at"]

    def __str__(self) -> str:
        return f"{self.label} x {self.quantity}"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    BANK = "bank", "Bank transfer"
    OTHER = "other", "Other"


class Payment(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    idempotency_key = models.CharField(max_length=128)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_recorded",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_payment_idempotency_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount} {self.method} ({self.order.bill_reference})"


class Refund(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="refunds",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="refunds",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=128)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_recorded",
    )
    restocked = models.BooleanField(
        default=False,
        help_text="If true, tracked inventory was increased for this refund.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_refund_idempotency_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"Refund {self.amount} ({self.order.bill_reference})"


class PosShiftStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class PosShift(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="pos_shifts",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="pos_shifts",
    )
    status = models.CharField(max_length=16, choices=PosShiftStatus.choices, default=PosShiftStatus.OPEN)
    opened_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_shifts_opened",
    )
    closed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_shifts_closed",
    )
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"{self.outlet.name} shift {self.status}"


class SupermarketLineReturn(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund = models.OneToOneField(
        Refund, on_delete=models.PROTECT, null=True, blank=True,
        related_name="line_return",
        help_text="Customer refund recorded with this physical return, if any.",
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="supermarket_returns",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="supermarket_returns",
    )
    order_line = models.ForeignKey(
        OrderLine,
        on_delete=models.CASCADE,
        related_name="supermarket_returns",
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    reason = models.CharField(max_length=255, blank=True)
    restocked = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supermarket_returns_created",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.order.bill_reference} return {self.quantity}"


class OfflineQueueStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"


class OfflineQueuedOperation(TimeStampedModel):
    """Client-side POS queue: idempotent replay when connectivity returns."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="offline_queue",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="offline_queue",
    )
    client_mutation_id = models.CharField(
        max_length=128,
        help_text="Unique per device/session; prevents duplicate apply.",
    )
    operation_type = models.CharField(
        max_length=32,
        help_text="e.g. order_payment, order_create",
    )
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=OfflineQueueStatus.choices,
        default=OfflineQueueStatus.PENDING,
    )
    error_message = models.TextField(blank=True)
    applied_payment_id = models.UUIDField(null=True, blank=True)
    applied_order_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_mutation_id"],
                name="uniq_offline_queue_client_mutation_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.operation_type} ({self.status})"
