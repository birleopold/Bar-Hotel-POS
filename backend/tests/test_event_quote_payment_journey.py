"""Connected event quotation, booking and actual customer payment workflow."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.events.models import (
    EventBooking, EventBookingStatus, EventPayment, EventPaymentMethod,
    EventQuoteStatus, EventSpace,
)
from apps.events.services_journey import (
    create_event_quote, change_event_quote_status, record_event_payment,
)
from apps.finance.models import CashbookEntry, FinancePostingLink, FinancePostingSource
from apps.tenants.models import Tenant, Site


class EventJourneyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Events Journey", slug="events-journey-tests")
        self.site = Site.objects.create(tenant=self.tenant, name="Main Function Hall")
        self.space = EventSpace.objects.create(
            tenant=self.tenant, site=self.site, name="Grand Hall", capacity=70,
        )
        self.user = User.objects.create_user(email="events.manager@example.com")
        self.member = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.SITE_MANAGER,
        )
        self.member.sites.add(self.site)
        start = timezone.now() + timedelta(days=8)
        self.booking = EventBooking.objects.create(
            tenant=self.tenant, space=self.space, title="Wedding",
            customer_name="Customer", start_at=start, end_at=start + timedelta(hours=4),
            status=EventBookingStatus.TENTATIVE, headcount=50,
            deposit_amount=Decimal("250000"),
        )

    def quote(self):
        return create_event_quote(
            booking=self.booking, membership=self.member, user=self.user,
            reference="EV-Q-001", amount=Decimal("1000000"),
            valid_until=timezone.localdate() + timedelta(days=2),
            description="Venue, setup and catering",
        )

    def accept(self):
        quote = self.quote()
        change_event_quote_status(
            quote=quote, membership=self.member, user=self.user, action="send",
        )
        return change_event_quote_status(
            quote=quote, membership=self.member, user=self.user, action="accept",
        )

    def test_quote_to_confirmed_booking_and_cashbook_payment_once(self):
        accepted = self.accept()
        self.assertEqual(accepted.status, EventQuoteStatus.ACCEPTED)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, EventBookingStatus.CONFIRMED)
        payment, replay = record_event_payment(
            booking=self.booking, membership=self.member, user=self.user,
            amount=Decimal("250000"), method=EventPaymentMethod.MOBILE_MONEY,
            reference="MM-001", idempotency_key="EVENT-MM-001",
        )
        same, repeated = record_event_payment(
            booking=self.booking, membership=self.member, user=self.user,
            amount=Decimal("250000"), method=EventPaymentMethod.MOBILE_MONEY,
            reference="MM-001", idempotency_key="EVENT-MM-001",
        )
        self.assertFalse(replay)
        self.assertTrue(repeated)
        self.assertEqual(payment.pk, same.pk)
        self.assertEqual(EventPayment.objects.filter(booking=self.booking).count(), 1)
        posted = FinancePostingLink.objects.get(
            tenant=self.tenant, source_type=FinancePostingSource.EVENT_PAYMENT,
            source_id=str(payment.pk),
        )
        self.assertEqual(posted.cashbook_entry.amount, Decimal("250000"))
        self.assertEqual(CashbookEntry.objects.filter(tenant=self.tenant).count(), 1)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.deposit_amount, Decimal("250000"))

    def test_cannot_receive_payment_before_quote_acceptance(self):
        with self.assertRaises(ValidationError):
            record_event_payment(
                booking=self.booking, membership=self.member, user=self.user,
                amount=Decimal("100"), method=EventPaymentMethod.CASH,
                idempotency_key="PREPAID-1",
            )
        self.assertFalse(EventPayment.objects.exists())

    def test_overpayment_and_conflicting_idempotency_key_rejected(self):
        self.accept()
        record_event_payment(
            booking=self.booking, membership=self.member, user=self.user,
            amount=Decimal("1000000"), method=EventPaymentMethod.CASH,
            idempotency_key="EVENT-FULL",
        )
        with self.assertRaises(ValidationError):
            record_event_payment(
                booking=self.booking, membership=self.member, user=self.user,
                amount=Decimal("1"), method=EventPaymentMethod.CASH,
                idempotency_key="EVENT-EXTRA",
            )
        with self.assertRaises(ValidationError):
            record_event_payment(
                booking=self.booking, membership=self.member, user=self.user,
                amount=Decimal("500"), method=EventPaymentMethod.CASH,
                idempotency_key="EVENT-FULL",
            )
        self.assertEqual(CashbookEntry.objects.filter(tenant=self.tenant).count(), 1)

    def test_overlapping_event_blocks_quote_acceptance(self):
        EventBooking.objects.create(
            tenant=self.tenant, space=self.space, title="Already held",
            customer_name="Other", start_at=self.booking.start_at,
            end_at=self.booking.end_at, status=EventBookingStatus.TENTATIVE,
        )
        quote = self.quote()
        change_event_quote_status(
            quote=quote, membership=self.member, user=self.user, action="send",
        )
        with self.assertRaises(ValidationError):
            change_event_quote_status(
                quote=quote, membership=self.member, user=self.user, action="accept",
            )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, EventBookingStatus.TENTATIVE)
