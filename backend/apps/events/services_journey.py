"""Event quotations and customer settlement.

An event deposit is actual money only when an EventPayment is recorded.
The older EventBooking.deposit_amount remains the planned/requested deposit.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.finance.models import FinanceCategoryKind, FinancePostingSource
from apps.finance.services import post_cashbook_for_source
from apps.staff.services import sites_visible_for_membership

from .models import (
    EventBooking, EventBookingStatus, EventPayment, EventPaymentMethod,
    EventQuote, EventQuoteStatus, EventSpace,
)


_MANAGER_ROLES = {
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
}


def _event_operator(booking, membership, user):
    if (
        not membership or not membership.is_active
        or membership.role not in _MANAGER_ROLES
        or membership.tenant_id != booking.tenant_id
        or not user or membership.user_id != user.pk
    ):
        raise ValidationError({"detail": "Only an authorized events manager can make this change."})
    visible_ids = {site.pk for site in sites_visible_for_membership(membership)}
    if booking.space.site_id not in visible_ids:
        raise ValidationError({"site": "This event is outside your permitted property."})


def _money(value):
    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError({"amount": "Enter a valid amount."}) from exc
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise ValidationError({"amount": "Enter a positive amount with at most two decimal places."})
    return amount


@transaction.atomic
def create_event_quote(*, booking, membership, user, reference, amount, valid_until, description=""):
    booking = EventBooking.objects.select_for_update().select_related("space").get(pk=booking.pk)
    _event_operator(booking, membership, user)
    if booking.status == EventBookingStatus.CANCELLED:
        raise ValidationError({"booking": "Cannot quote a cancelled booking."})
    number = (reference or "").strip()
    if not number or len(number) > 128:
        raise ValidationError({"reference": "Enter a quote number of up to 128 characters."})
    if not valid_until or valid_until < timezone.localdate():
        raise ValidationError({"valid_until": "Use today or a future validity date."})
    details = (description or "").strip()
    if len(details) > 5000:
        raise ValidationError({"description": "Use at most 5000 characters."})
    amount = _money(amount)
    if EventQuote.objects.filter(
        tenant_id=booking.tenant_id, booking=booking, reference=number,
    ).exists():
        raise ValidationError({"reference": "That quote number already exists for this booking."})
    quote = EventQuote.objects.create(
        tenant_id=booking.tenant_id, booking=booking, reference=number,
        amount=amount, description=details, valid_until=valid_until, created_by=user,
    )
    log_audit(
        tenant_id=booking.tenant_id, user_id=user.pk,
        action="events.quote_created", entity_type="event_quote",
        entity_id=str(quote.pk), payload={
            "booking_id": str(booking.pk), "amount": str(amount), "reference": number,
        },
    )
    return quote


@transaction.atomic
def change_event_quote_status(*, quote, membership, user, action):
    quote = EventQuote.objects.select_for_update().select_related(
        "booking__space",
    ).get(pk=quote.pk)
    booking = EventBooking.objects.select_for_update().get(pk=quote.booking_id)
    _event_operator(quote.booking, membership, user)
    if booking.status == EventBookingStatus.CANCELLED:
        raise ValidationError({"booking": "Cancelled bookings cannot accept quotations."})
    next_state = {
        (EventQuoteStatus.DRAFT, "send"): EventQuoteStatus.SENT,
        (EventQuoteStatus.SENT, "accept"): EventQuoteStatus.ACCEPTED,
    }.get((quote.status, action))
    if not next_state:
        raise ValidationError({"status": "Only draft quotes can be sent and sent quotes can be accepted."})
    if action == "accept":
        if quote.valid_until < timezone.localdate():
            raise ValidationError({"valid_until": "Quote expired. Create a new one."})
        if booking.quotes.exclude(pk=quote.pk).filter(status=EventQuoteStatus.ACCEPTED).exists():
            raise ValidationError({"status": "A different quote has already been accepted."})
        # Serialize confirmation of bookings sharing one event space.
        EventSpace.objects.select_for_update().get(pk=booking.space_id, tenant=booking.tenant)
        overlapping = EventBooking.objects.filter(
            tenant=booking.tenant, space_id=booking.space_id,
            start_at__lt=booking.end_at, end_at__gt=booking.start_at,
        ).exclude(pk=booking.pk).exclude(status=EventBookingStatus.CANCELLED)
        if overlapping.exists():
            raise ValidationError({"date": "Another event already holds this space during those times."})
        quote.accepted_at = timezone.now()
        quote.save(update_fields=["status", "accepted_at", "updated_at"] if False else ["accepted_at", "updated_at"])
        booking.status = EventBookingStatus.CONFIRMED
        booking.save(update_fields=["status", "updated_at"])
    quote.status = next_state
    quote.save(update_fields=["status", "updated_at"])
    log_audit(
        tenant_id=booking.tenant_id, user_id=user.pk,
        action="events.quote_status_changed", entity_type="event_quote",
        entity_id=str(quote.pk), payload={
            "status": quote.status, "booking_id": str(booking.pk),
        },
    )
    return quote


@transaction.atomic
def record_event_payment(*, booking, membership, user, amount, method, reference="", idempotency_key=""):
    booking = EventBooking.objects.select_for_update().select_related("space__site").get(pk=booking.pk)
    _event_operator(booking, membership, user)
    key = (idempotency_key or "").strip()
    if not key or len(key) > 128:
        raise ValidationError({"idempotency_key": "A payment request key is required."})
    amount = _money(amount)
    reference = (reference or "").strip()
    if len(reference) > 128:
        raise ValidationError({"reference": "Use at most 128 characters."})
    if method not in {item.value for item in EventPaymentMethod}:
        raise ValidationError({"method": "Choose a supported payment method."})
    existing = EventPayment.objects.filter(tenant_id=booking.tenant_id, idempotency_key=key).first()
    if existing:
        if (existing.booking_id != booking.pk or existing.amount != amount
                or existing.method != method or existing.reference != reference):
            raise ValidationError({"idempotency_key": "Payment key already used for a different transaction."})
        return existing, True
    if booking.status == EventBookingStatus.CANCELLED:
        raise ValidationError({"booking": "Cannot receive money for a cancelled event."})
    accepted = booking.quotes.filter(status=EventQuoteStatus.ACCEPTED).first()
    if not accepted:
        raise ValidationError({"booking": "Accept a quotation before recording event payments."})
    already_paid = booking.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    if amount > accepted.amount - already_paid:
        raise ValidationError({"amount": "Payment exceeds the remaining accepted quote amount."})
    payment = EventPayment.objects.create(
        tenant=booking.tenant, booking=booking,
        amount=amount, method=method, reference=reference,
        idempotency_key=key, recorded_by=user,
    )
    # Actual payment is posted once as cashbook income. This deposit is NOT
    # automatically fiscalised: tax point and EFRIS treatment need explicit review.
    post_cashbook_for_source(
        tenant_id=booking.tenant_id, source_type=FinancePostingSource.EVENT_PAYMENT,
        source_id=str(payment.pk), kind=FinanceCategoryKind.INCOME,
        amount=amount, site=booking.space.site,
        reference=(reference or accepted.reference)[:64],
        note=f"Event customer payment for {booking.title}",
        created_by=user, transaction_date=timezone.localdate(),
        default_category_name="Event Customer Payments", enqueue_efris=False,
    )
    log_audit(
        tenant_id=booking.tenant_id, user_id=user.pk,
        action="events.payment_received", entity_type="event_payment",
        entity_id=str(payment.pk), payload={
            "booking_id": str(booking.pk), "amount": str(amount), "method": method,
        },
    )
    return payment, False
