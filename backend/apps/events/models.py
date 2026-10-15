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
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True, related_name="event_bookings")
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


class EventQuoteStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    ACCEPTED = "accepted", "Accepted"


class EventQuote(TimeStampedModel):
    """Versioned event quotation attached to a customer booking."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="event_quotes")
    booking = models.ForeignKey(EventBooking, on_delete=models.PROTECT, related_name="quotes")
    reference = models.CharField(max_length=128)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    description = models.TextField(blank=True)
    valid_until = models.DateField()
    status = models.CharField(max_length=16, choices=EventQuoteStatus.choices, default=EventQuoteStatus.DRAFT)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_quotes_created")
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "booking", "reference"], name="uniq_event_quote_number_booking"),
        ]


class EventPaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    BANK = "bank", "Bank transfer"
    OTHER = "other", "Other"


class EventPayment(TimeStampedModel):
    """Actual customer deposit or settlement, not a requested deposit figure."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="event_payments")
    booking = models.ForeignKey(EventBooking, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=16, choices=EventPaymentMethod.choices)
    reference = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128)
    recorded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_payments_recorded")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="uniq_event_payment_key_tenant"),
        ]
