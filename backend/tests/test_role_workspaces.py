from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole
from apps.lodging.models import Reservation, ReservationStatus
from apps.pos.models import Order
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_SITE_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class RoleWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Workspaces", slug="role-workspaces")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Hotel")
        cls.other_site = Site.objects.create(tenant=cls.tenant, name="Other branch")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Bar", outlet_type=OutletType.BAR)
        cls.other_outlet = Outlet.objects.create(site=cls.other_site, name="Other bar", outlet_type=OutletType.BAR)
        cls.server = get_user_model().objects.create_user(email="workspace-server@test.local", password="Password9!")
        cls.reception = get_user_model().objects.create_user(email="workspace-reception@test.local", password="Password9!")
        cls.other_worker = get_user_model().objects.create_user(email="workspace-other@test.local", password="Password9!")
        membership = Membership.objects.create(tenant=cls.tenant, user=cls.server, role=MembershipRole.SERVER)
        membership.outlets.add(cls.outlet)
        membership = Membership.objects.create(tenant=cls.tenant, user=cls.reception, role=MembershipRole.FRONT_DESK)
        membership.sites.add(cls.site)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_SITE_KEY] = str(self.site.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_floor_actions_create_only_on_post_and_scope_my_orders(self):
        self.login(self.server)
        response = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(response.status_code, 200)
        actions = response.context["staff_dashboard_primary_actions"]
        self.assertIn("My orders", [a.label for a in actions])
        new = next(a for a in actions if a.label == "New order")
        self.assertEqual(new.method, "post")
        before = Order.objects.count()
        self.client.get(new.url)
        self.assertEqual(Order.objects.count(), before)
        self.client.post(new.url)
        own = Order.objects.get(created_by=self.server)
        other = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.other_worker)
        hidden = Order.objects.create(tenant=self.tenant, outlet=self.other_outlet, created_by=self.server)
        response = self.client.get(reverse("staff-orders"), {"mine": "1", "status": "open"})
        self.assertEqual(list(response.context["orders"]), [own])
        self.assertNotIn(other, response.context["orders"])
        self.assertNotIn(hidden, response.context["orders"])
        self.assertContains(response, 'name="mine" value="1"')

    def test_reception_lanes_filter_status_dates_and_branch(self):
        self.login(self.reception)
        today = timezone.localdate()
        def stay(name, start, end, status, site=None):
            return Reservation.objects.create(tenant=self.tenant, site=site or self.site, guest_name=name, check_in=start, check_out=end, status=status)
        arrival = stay("Expected", today, today + timedelta(days=2), ReservationStatus.CONFIRMED)
        stay("Cancelled", today, today + timedelta(days=1), ReservationStatus.CANCELLED)
        stay("Tomorrow", today + timedelta(days=1), today + timedelta(days=2), ReservationStatus.CONFIRMED)
        stay("Other branch", today, today + timedelta(days=1), ReservationStatus.CONFIRMED, self.other_site)
        departure = stay("Due today", today - timedelta(days=2), today, ReservationStatus.CHECKED_IN)
        overdue = stay("Overdue", today - timedelta(days=3), today - timedelta(days=1), ReservationStatus.CHECKED_IN)
        in_house = stay("Staying", today, today + timedelta(days=2), ReservationStatus.CHECKED_IN)
        route = reverse("staff-lodging-reservations")
        for lane, expected in [("arrivals", {arrival}), ("departures", {departure, overdue}), ("in_house", {departure, overdue, in_house})]:
            response = self.client.get(route, {"lane": lane})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.context["reservations"]), expected)
        response = self.client.get(route, {"lane": "arrivals", "status": "cancelled"})
        self.assertContains(response, "No stays match this task")
        self.assertNotContains(response, "Create your first reservation")
        response = self.client.get(reverse("staff-dashboard"))
        self.assertEqual([a.label for a in response.context["staff_dashboard_primary_actions"]], ["Arrivals", "Departures", "In-house", "Rooms", "New reservation"])
        self.assertNotContains(response, 'action="' + reverse("staff-order-quick-create") + '"')
