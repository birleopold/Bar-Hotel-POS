from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.customers.models import Customer
from apps.customers.services import merge_customers
from apps.events.models import EventBooking, EventSpace
from apps.lodging.models import Folio, Reservation
from apps.pos.models import Order
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class SharedCustomerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Guest Identity", slug="guest-identity")
        cls.other_tenant = Tenant.objects.create(name="Other Identity", slug="other-identity")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.other_site = Site.objects.create(tenant=cls.tenant, name="Branch B")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Retail", outlet_type=OutletType.RETAIL)
        cls.other_outlet = Outlet.objects.create(site=cls.other_site, name="Remote", outlet_type=OutletType.RETAIL)
        cls.user = User.objects.create_user(email="owner@identity.test", password="TestPass9!")
        cls.membership = Membership.objects.create(tenant=cls.tenant, user=cls.user, role=MembershipRole.OWNER)
        cls.worker = User.objects.create_user(email="branch@identity.test", password="TestPass9!")
        cls.worker_membership = Membership.objects.create(tenant=cls.tenant, user=cls.worker, role=MembershipRole.FRONT_DESK)
        cls.worker_membership.sites.add(cls.site)

    def login(self, user=None):
        self.client.force_login(user or self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_explicit_merge_keeps_snapshots_and_rejects_cross_tenant(self):
        source = Customer.objects.create(tenant=self.tenant, name="A Guest", email="a@example.test")
        target = Customer.objects.create(tenant=self.tenant, name="Alice Guest", email="a@example.test")
        other = Customer.objects.create(tenant=self.other_tenant, name="Alice Guest", email="a@example.test")
        reservation = Reservation.objects.create(tenant=self.tenant, site=self.site, customer=source,
            guest_name="Name on original booking", check_in=date.today(), check_out=date.today()+timedelta(days=1))
        folio = Folio.objects.create(tenant=self.tenant, site=self.site, customer=source,
            reservation=reservation, guest_name="Original folio name")
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, customer=source, total=Decimal("25"))
        space = EventSpace.objects.create(tenant=self.tenant, site=self.site, name="Hall")
        booking = EventBooking.objects.create(tenant=self.tenant, space=space, customer=source,
            title="Dinner", customer_name="Name on original event", start_at=timezone.now(), end_at=timezone.now()+timedelta(hours=2))
        with self.assertRaises(ValidationError):
            merge_customers(source=source, target=other, tenant_id=self.tenant.pk, user=self.user, reason="Same person")
        with self.assertRaises(ValidationError):
            merge_customers(source=source, target=target, tenant_id=self.tenant.pk, user=self.user, reason="")
        merged, counts = merge_customers(source=source, target=target, tenant_id=self.tenant.pk,
            user=self.user, reason="Identity confirmed by customer")
        self.assertEqual(merged.pk, target.pk)
        self.assertEqual(counts, {"reservations": 1, "folios": 1, "orders": 1, "events": 1})
        source.refresh_from_db(); reservation.refresh_from_db(); folio.refresh_from_db(); order.refresh_from_db(); booking.refresh_from_db()
        self.assertEqual(source.merged_into_id, target.pk)
        self.assertEqual({reservation.customer_id, folio.customer_id, order.customer_id, booking.customer_id}, {target.pk})
        self.assertEqual(reservation.guest_name, "Name on original booking")
        self.assertEqual(booking.customer_name, "Name on original event")
        with self.assertRaises(ValidationError):
            merge_customers(source=source, target=target, tenant_id=self.tenant.pk, user=self.user, reason="Replay")

    def test_staff_directory_scope_and_explicit_order_link(self):
        self.login()
        response = self.client.post(reverse("staff-customer-create"), {"name": "A Guest", "email": "A@EXAMPLE.TEST", "phone": "123"})
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get(tenant=self.tenant, name="A Guest")
        self.assertEqual(customer.email, "a@example.test")
        remote = Customer.objects.create(tenant=self.tenant, name="Remote", created_by=self.user)
        remote_order = Order.objects.create(tenant=self.tenant, outlet=self.other_outlet, customer=remote)
        Customer.objects.create(tenant=self.other_tenant, name="Private")
        self.assertContains(self.client.get(reverse("staff-customers")), "A Guest")
        self.assertNotContains(self.client.get(reverse("staff-customers")), "Private")
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet)
        response = self.client.post(reverse("staff-order-detail", args=[order.pk]), {"action": "set_customer", "customer_id": str(customer.pk)})
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db(); self.assertEqual(order.customer_id, customer.pk)
        self.assertContains(self.client.get(reverse("staff-customer-detail", args=[customer.pk])), str(order.bill_reference or order.pk))
        self.login(self.worker)
        self.assertEqual(self.client.get(reverse("staff-customer-detail", args=[remote.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("staff-customer-detail", args=[customer.pk])).status_code, 200)
        self.assertNotContains(self.client.get(reverse("staff-customer-detail", args=[customer.pk])), str(remote_order.pk))
        self.assertEqual(self.client.get(reverse("staff-customers")).status_code, 200)

    def test_reservation_and_event_forms_reject_other_tenant_customer(self):
        from apps.staff.forms.events import StaffEventBookingForm
        from apps.staff.forms.lodging import StaffReservationForm
        other = Customer.objects.create(tenant=self.other_tenant, name="Other")
        own = Customer.objects.create(tenant=self.tenant, name="Mine", created_by=self.user)
        reservation_data = {"customer": str(other.pk), "guest_name": "Other", "check_in": "2026-10-01", "check_out": "2026-10-02"}
        form = StaffReservationForm(reservation_data, membership=self.membership, user=self.user)
        self.assertFalse(form.is_valid())
        reservation_data["customer"] = str(own.pk)
        self.assertTrue(StaffReservationForm(reservation_data, membership=self.membership, user=self.user).is_valid())
        space = EventSpace.objects.create(tenant=self.tenant, site=self.site, name="Room")
        data = {"space": str(space.pk), "title": "Meeting", "customer": str(other.pk), "customer_name": "Other",
            "start_at": "2026-10-01T10:00", "end_at": "2026-10-01T11:00", "status": "tentative", "headcount": 1, "deposit_amount": "0"}
        form = StaffEventBookingForm(data, tenant=self.tenant, event_site=self.site, membership=self.membership, user=self.user)
        self.assertFalse(form.is_valid())
        data["customer"] = str(own.pk)
        self.assertTrue(StaffEventBookingForm(data, tenant=self.tenant, event_site=self.site, membership=self.membership, user=self.user).is_valid())
