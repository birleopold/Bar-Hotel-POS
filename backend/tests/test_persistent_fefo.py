from datetime import date
from decimal import Decimal
from django.test import TestCase

from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.batches import InventoryBatch
from apps.inventory.fefo import InsufficientBatchStock
from apps.inventory.services_batches import available_fefo_plan
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class PersistentFefoTests(TestCase):
    def test_plan_uses_only_unexpired_nonquarantined_batches(self):
        tenant = Tenant.objects.create(name="Batch Stock", slug="batch-stock-test")
        site = Site.objects.create(tenant=tenant, name="Main")
        outlet = Outlet.objects.create(site=site, name="Shop", outlet_type=OutletType.RETAIL)
        category = MenuCategory.objects.create(tenant=tenant, name="Stock")
        item = MenuItem.objects.create(tenant=tenant, category=category, name="Milk", unit_price=Decimal("1000"))
        def batch(code, qty, expiry, quarantine=False):
            return InventoryBatch.objects.create(
                tenant=tenant, outlet=outlet, menu_item=item, batch_code=code,
                received_at=date(2026, 10, 1), expiry_date=expiry,
                received_quantity=qty, remaining_quantity=qty, quarantined=quarantine,
            )
        early = batch("EARLY", Decimal("2"), date(2026, 10, 20))
        late = batch("LATE", Decimal("6"), date(2026, 11, 1))
        batch("EXPIRED", Decimal("99"), date(2026, 10, 1))
        batch("HOLD", Decimal("99"), date(2026, 10, 17), True)
        plan = available_fefo_plan(
            tenant=tenant, outlet=outlet, menu_item=item,
            quantity=Decimal("5"), as_of=date(2026, 10, 15),
        )
        self.assertEqual(plan, [(early.id, Decimal("2")), (late.id, Decimal("3"))])
        with self.assertRaises(InsufficientBatchStock):
            available_fefo_plan(tenant=tenant, outlet=outlet, menu_item=item,
                                quantity=Decimal("9"), as_of=date(2026, 10, 15))
