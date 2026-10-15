"""KDS workflow regression tests for fast start, optional acceptance and manager recall."""
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User, Membership, MembershipRole
from apps.pos.models import Order, OrderLine, OrderStatus, KdsLineStatus
from apps.pos.services.kds import update_order_line_kds_status, manage_kds_item
from apps.tenants.models import Tenant, Site, Outlet, OutletType


class KdsProductionWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Kitchen Workflow", slug="kitchen-workflow-tests")
        site = Site.objects.create(tenant=self.tenant, name="Restaurant")
        self.outlet = Outlet.objects.create(site=site, name="Kitchen", outlet_type=OutletType.RESTAURANT)
        self.manager = User.objects.create_user(email="kds.manager@example.com")
        self.chef = User.objects.create_user(email="kds.chef@example.com")
        self.manager_membership = Membership.objects.create(
            tenant=self.tenant, user=self.manager, role=MembershipRole.SITE_MANAGER,
        )
        self.chef_membership = Membership.objects.create(
            tenant=self.tenant, user=self.chef, role=MembershipRole.KITCHEN,
        )
        self.manager_membership.sites.add(site)
        self.chef_membership.sites.add(site)
        self.order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.chef)
        self.line = OrderLine.objects.create(
            order=self.order, label="Chicken and rice", quantity="1",
            unit_price="18000.00", line_total="18000.00", kds_station="kitchen",
        )

    def step(self, status):
        return update_order_line_kds_status(
            order=self.order, line=self.line, kds_status=status,
            kds_station=None, user=self.chef,
        )

    def test_optional_acceptance_then_preparation_and_ready(self):
        self.step(KdsLineStatus.ACCEPTED)
        self.step(KdsLineStatus.IN_PREP)
        self.step(KdsLineStatus.READY)
        self.line.refresh_from_db()
        self.assertEqual(self.line.kds_status, KdsLineStatus.READY)
        self.assertIsNotNone(self.line.kds_status_changed_at)

    def test_one_tap_legacy_start_still_works(self):
        self.step(KdsLineStatus.IN_PREP)
        self.line.refresh_from_db()
        self.assertEqual(self.line.kds_status, KdsLineStatus.IN_PREP)

    def test_cannot_skip_directly_to_ready(self):
        with self.assertRaises(ValidationError):
            self.step(KdsLineStatus.READY)
        self.line.refresh_from_db()
        self.assertEqual(self.line.kds_status, KdsLineStatus.PENDING)

    def test_manager_rush_and_recall_have_safe_guards(self):
        self.step(KdsLineStatus.IN_PREP)
        self.step(KdsLineStatus.READY)
        ln, changed = manage_kds_item(
            order=self.order, line=self.line, membership=self.manager_membership,
            user=self.manager, action="rush",
        )
        self.assertTrue(changed)
        self.assertTrue(ln.kds_rush)
        with self.assertRaises(ValidationError):
            manage_kds_item(
                order=self.order, line=self.line, membership=self.manager_membership,
                user=self.manager, action="recall", reason="",
            )
        ln, changed = manage_kds_item(
            order=self.order, line=self.line, membership=self.manager_membership,
            user=self.manager, action="recall", reason="Incorrect garnish",
        )
        self.assertTrue(changed)
        self.assertEqual(ln.kds_status, KdsLineStatus.IN_PREP)
        with self.assertRaises(ValidationError):
            manage_kds_item(
                order=self.order, line=self.line, membership=self.manager_membership,
                user=self.manager, action="recall", reason="Duplicate attempt",
            )

    def test_chef_cannot_change_rush_priority(self):
        with self.assertRaises(ValidationError):
            manage_kds_item(
                order=self.order, line=self.line, membership=self.chef_membership,
                user=self.chef, action="rush",
            )
        self.line.refresh_from_db()
        self.assertFalse(self.line.kds_rush)

    def test_paid_closed_order_remains_in_prep_until_served(self):
        self.order.status = OrderStatus.CLOSED
        self.order.is_paid = True
        self.order.save(update_fields=["status", "is_paid"])
        self.step(KdsLineStatus.IN_PREP)
        self.step(KdsLineStatus.READY)
        self.step(KdsLineStatus.SERVED)
        self.line.refresh_from_db()
        self.assertEqual(self.line.kds_status, KdsLineStatus.SERVED)

    def test_cancelled_order_cannot_enter_prep(self):
        self.order.status = OrderStatus.CANCELLED
        self.order.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            self.step(KdsLineStatus.IN_PREP)
