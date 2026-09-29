import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.common.models import TimeStampedModel


class EventSpace(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="event_spaces",
    )
    site = models.ForeignKey(
        "tenants.Site",
        on_delete=models.CASCADE,
        related_name="event_spaces",
    )
    name = models.CharField(max_length=255)
    capacity = models.PositiveIntegerField(default=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["site", "name"]
        unique_together = [["site", "name"]]

    def __str__(self) -> str:
        return f"{self.site.name}:{self.name}"


class EventBookingStatus(models.TextChoices):
    TENTATIVE = "tentative", "Tentative"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"


class EventBooking(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="event_bookings",
    )
    space = models.ForeignKey(
        EventSpace,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    title = models.CharField(max_length=255)
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=32, blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=EventBookingStatus.choices,
        default=EventBookingStatus.TENTATIVE,
    )
    headcount = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    notes = models.TextField(blank=True)
    deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["start_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="events_booking_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.start_at})"
