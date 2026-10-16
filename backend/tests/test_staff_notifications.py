"""Staff notification deduplication, access and read-state tests."""
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import StaffNotification
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance
from apps.staff.services.alerts import mark_alerts_read, refresh_staff_alerts
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class StaffNotificationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Alert Tenant", slug="alerts-test-tenant")
        self.site_a = Site.objects.create(tenant=self.tenant, name="A")
        self.site_b = Site.objects.create(tenant=self.tenant, name="B")
        self.outlet_a = Outlet.objects.create(
            site=self.site_a, name="Shop A", outlet_type=OutletType.RETAIL,
        )
        self.outlet_b = Outlet.objects.create(
            site=self.site_b, name="Shop B", outlet_type=OutletType.RETAIL,
        )
        self.worker_a = User.objects.create_user(email="alerts.a@example.org")
        self.worker_b = User.objects.create_user(email="alerts.b@example.org")
        self.membership_a = Membership.objects.create(
            tenant=self.tenant, user=self.worker_a, role=MembershipRole.SITE_MANAGER,
        )
        self.membership_a.sites.add(self.site_a)
        self.membership_b = Membership.objects.create(
            tenant=self.tenant, user=self.worker_b, role=MembershipRole.SITE_MANAGER,
        )
        self.membership_b.sites.add(self.site_b)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Grocery")
        self.product = MenuItem.objects.create(
            tenant=self.tenant, category=self.category, name="Milk",
            track_inventory=True, reorder_level=Decimal("8"),
            unit_price=Decimal("3000"),
        )
        self.stock_a = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet_a,
            menu_item=self.product, quantity=Decimal("2"),
        )
        self.stock_b = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet_b,
            menu_item=self.product, quantity=Decimal("1"),
        )

    def test_site_scoped_alerts_are_private_and_deduplicated(self):
        first = refresh_staff_alerts(tenant=self.tenant, membership=self.membership_a)
        second = refresh_staff_alerts(tenant=self.tenant, membership=self.membership_a)
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        qs = StaffNotification.objects.filter(recipient=self.membership_a)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().source_id, str(self.stock_a.pk))
        self.assertNotIn(str(self.stock_b.pk), [a.source_id for a in qs])

    def test_mark_read_does_not_mark_other_workers_notifications(self):
        refresh_staff_alerts(tenant=self.tenant, membership=self.membership_a)
        refresh_staff_alerts(tenant=self.tenant, membership=self.membership_b)
        own = StaffNotification.objects.get(recipient=self.membership_a)
        changed = mark_alerts_read(
            tenant=self.tenant, membership=self.membership_a,
            ids=[own.pk],
        )
        self.assertEqual(changed, 1)
        self.assertIsNotNone(
            StaffNotification.objects.get(pk=own.pk).read_at,
        )
        self.assertIsNone(
            StaffNotification.objects.get(recipient=self.membership_b).read_at,
        )

    def test_stock_recovery_archives_alert_without_deleting_evidence(self):
        refresh_staff_alerts(tenant=self.tenant, membership=self.membership_a)
        self.stock_a.quantity = Decimal("30")
        self.stock_a.save(update_fields=["quantity"])
        refresh_staff_alerts(tenant=self.tenant, membership=self.membership_a)
        row = StaffNotification.objects.get(recipient=self.membership_a)
        self.assertFalse(row.active)

    def test_empty_membership_cannot_refresh_other_tenant(self):
        unrelated = Tenant.objects.create(name="Other Alert Tenant", slug="other-alert-fixture")
        self.assertEqual(
            refresh_staff_alerts(tenant=unrelated, membership=self.membership_a), 0,
        )
        self.assertFalse(StaffNotification.objects.exists())
