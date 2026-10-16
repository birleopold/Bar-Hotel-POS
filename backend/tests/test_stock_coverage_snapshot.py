from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance, StockMovement, StockReason
from apps.inventory.services_intelligence import stock_coverage_snapshot
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class StockCoverageSnapshotTests(TestCase):
    def test_sales_velocity_and_scope(self):
        tenant = Tenant.objects.create(name="Coverage", slug="coverage-tests")
        site = Site.objects.create(tenant=tenant, name="Shop")
        outlet = Outlet.objects.create(site=site, name="Counter", outlet_type=OutletType.RETAIL)
        remote = Outlet.objects.create(site=site, name="Remote", outlet_type=OutletType.RETAIL)
        category = MenuCategory.objects.create(tenant=tenant, name="Drinks")
        item = MenuItem.objects.create(
            tenant=tenant, category=category, name="Juice",
            unit_price=Decimal("2000"), track_inventory=True, reorder_level=Decimal("8"),
        )
        StockBalance.objects.create(tenant=tenant, outlet=outlet, menu_item=item, quantity=Decimal("6"))
        StockBalance.objects.create(tenant=tenant, outlet=remote, menu_item=item, quantity=Decimal("100"))
        StockMovement.objects.create(
            tenant=tenant, outlet=outlet, menu_item=item, quantity_change=Decimal("-30"),
            reason=StockReason.SALE,
        )
        rows = stock_coverage_snapshot(tenant=tenant, outlet=outlet, days=30)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["units_sold_window"], Decimal("30"))
        self.assertEqual(rows[0]["daily_velocity"], Decimal("1"))
        self.assertEqual(rows[0]["days_remaining"], Decimal("6"))
        self.assertTrue(rows[0]["below_reorder_level"])
        self.assertEqual(rows[0]["reorder_shortfall"], Decimal("2"))
        self.assertFalse(rows[0]["out_of_stock"])
        self.assertEqual(rows[0]["sell_through_proxy"], Decimal("30") / Decimal("36"))

    def test_zero_stock_is_explicit_and_does_not_invent_demand(self):
        tenant = Tenant.objects.create(name="Grocery stockout", slug="grocery-stockout")
        site = Site.objects.create(tenant=tenant, name="Store")
        outlet = Outlet.objects.create(site=site, name="Main till", outlet_type=OutletType.SUPERMARKET)
        category = MenuCategory.objects.create(tenant=tenant, name="Groceries")
        item = MenuItem.objects.create(
            tenant=tenant, category=category, name="Rice",
            unit_price=Decimal("3500"), track_inventory=True,
            reorder_level=Decimal("15"),
        )
        StockBalance.objects.create(
            tenant=tenant, outlet=outlet, menu_item=item, quantity=Decimal("0"),
        )
        row = stock_coverage_snapshot(tenant=tenant, outlet=outlet)[0]
        self.assertTrue(row["out_of_stock"])
        self.assertTrue(row["no_sales_history"])
        self.assertIsNone(row["days_remaining"])
        self.assertEqual(row["reorder_shortfall"], Decimal("15"))

    def test_window_validation(self):
        with self.assertRaises(ValueError):
            stock_coverage_snapshot(tenant=None, outlet=None, days=0)

    def test_rejects_cross_tenant_outlet(self):
        tenant = Tenant.objects.create(name="Tenant A", slug="coverage-tenant-a")
        other = Tenant.objects.create(name="Tenant B", slug="coverage-tenant-b")
        other_site = Site.objects.create(tenant=other, name="Other site")
        outlet = Outlet.objects.create(site=other_site, name="Other counter", outlet_type=OutletType.RETAIL)
        with self.assertRaisesRegex(ValueError, "outlet must belong to tenant"):
            stock_coverage_snapshot(tenant=tenant, outlet=outlet)
