import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.common.models import TimeStampedModel


class RoomType(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="room_types",
    )
    site = models.ForeignKey(
        "tenants.Site",
        on_delete=models.CASCADE,
        related_name="room_types",
    )
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    max_occupancy = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["site", "name"]
        unique_together = [["site", "name"]]

    def __str__(self) -> str:
        return f"{self.site.name}:{self.name}"


class RoomRateWindow(TimeStampedModel):
    """Seasonal or promotional nightly rate for a room type (advanced rates / yield-lite)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        related_name="rate_windows",
    )
    label = models.CharField(max_length=128, blank=True)
    valid_from = models.DateField()
    valid_to = models.DateField(
        null=True,
        blank=True,
        help_text="Null = open-ended from valid_from.",
    )
    nightly_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["room_type", "valid_from"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="lodging_roomratewindow_valid_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.room_type.name} {self.valid_from}"


class RoomStatus(models.TextChoices):
    CLEAN = "clean", "Clean"
    DIRTY = "dirty", "Dirty"
    INSPECTED = "inspected", "Inspected"
    OUT_OF_ORDER = "out_of_order", "Out of order"


class Room(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        related_name="rooms",
    )
    name = models.CharField(max_length=64, help_text="Room number or label.")
    status = models.CharField(
        max_length=20,
        choices=RoomStatus.choices,
        default=RoomStatus.CLEAN,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["room_type", "name"]
        unique_together = [["room_type", "name"]]

    def __str__(self) -> str:
        return f"{self.room_type}:{self.name}"


class MaintenanceStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In progress"
    RESOLVED = "resolved", "Resolved"


class MaintenancePriority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class RoomMaintenanceRequest(TimeStampedModel):
    """Accountable repair work for a room, separate from its availability status."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="room_maintenance_requests")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="maintenance_requests")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=12, choices=MaintenancePriority.choices, default=MaintenancePriority.NORMAL)
    status = models.CharField(max_length=16, choices=MaintenanceStatus.choices, default=MaintenanceStatus.OPEN)
    assigned_to = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_maintenance_assignments",
    )
    expected_by = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_maintenance_requests_created",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-priority", "expected_by", "-created_at"]

    def __str__(self) -> str:
        return f"{self.room.name}: {self.title}"


class ReservationStatus(models.TextChoices):
    HELD = "held", "Held"
    CONFIRMED = "confirmed", "Confirmed"
    CHECKED_IN = "checked_in", "Checked in"
    CHECKED_OUT = "checked_out", "Checked out"
    CANCELLED = "cancelled", "Cancelled"


class Reservation(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    site = models.ForeignKey(
        "tenants.Site",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    guest_name = models.CharField(max_length=255)
    guest_email = models.EmailField(blank=True)
    guest_phone = models.CharField(max_length=32, blank=True)
    check_in = models.DateField()
    check_out = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.CONFIRMED,
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-check_in", "guest_name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(check_out__gt=F("check_in")),
                name="lodging_reservation_check_out_after_check_in",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.guest_name} ({self.check_in} → {self.check_out})"


class FolioStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class Folio(TimeStampedModel):
    """Guest or house account; POS charges can post here when the order is paid."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="folios",
    )
    site = models.ForeignKey(
        "tenants.Site",
        on_delete=models.CASCADE,
        related_name="folios",
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folios",
    )
    guest_name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16,
        choices=FolioStatus.choices,
        default=FolioStatus.OPEN,
    )
    currency = models.CharField(max_length=3, default="USD")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Folio {self.guest_name} ({self.status})"


class FolioLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="folio_lines",
    )
    folio = models.ForeignKey(
        Folio,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    description = models.CharField(max_length=512)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )
    source_order = models.ForeignKey(
        "pos.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folio_lines",
    )

    class Meta:
        ordering = ["folio", "created_at"]

    def __str__(self) -> str:
        return f"{self.description} {self.amount}"


class FolioPaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    BANK = "bank", "Bank transfer"
    OTHER = "other", "Other"


class FolioPayment(TimeStampedModel):
    """An immutable settlement received against a guest folio."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="folio_payments",
    )
    folio = models.ForeignKey(Folio, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    method = models.CharField(max_length=20, choices=FolioPaymentMethod.choices)
    reference = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folio_payments_recorded",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_folio_payment_idempotency_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount} {self.method} ({self.folio.guest_name})"
