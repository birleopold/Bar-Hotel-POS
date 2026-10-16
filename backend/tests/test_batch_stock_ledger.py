"""Regression coverage for the batch-aware stock ledger and legacy stock labeling."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.batches import InventoryBatch
from apps.inventory.models import StockBalance, StockMovement, StockReason, StockBatchAllocation
from apps.inventory.services import apply_manual_stock_change
from apps.inventory.services_batches import (
    label_existing_stock_batch, waste_batch_stock, change_batch_hold, hold_matching_lot,
)
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class BatchStockLedgerTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Stock Ledger", slug="stock-ledger-fefo")
        site = Site.objects.create(tenant=self.tenant, name="Store")
        self.outlet = Outlet.objects.create(site=site, name="Main", outlet_type=OutletType.RETAIL)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Tracked")
        self.item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Yogurt",
            unit_price=Decimal("1500"), track_inventory=True,
        )
        self.balance = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            quantity=Decimal("8"),
        )



    def test_fefo_outflow_rejects_invalid_quantities_even_without_batches(self):
        from apps.inventory.services_batches import consume_for_outflow_if_batched
        for quantity in ("NaN", "Infinity", "-1", "0", "1.0001", "invalid"):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError):
                    consume_for_outflow_if_batched(
                        tenant_id=self.tenant.id, outlet_id=self.outlet.id,
                        menu_item_id=self.item.id, quantity=quantity,
                    )
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, Decimal("8"))
    def batch(self, code, amount, expires):
        return InventoryBatch.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            batch_code=code, received_at=date(2026, 1, 1),
            expiry_date=expires, received_quantity=amount,
            remaining_quantity=amount,
        )

    def test_manual_outflow_consumes_earliest_batch_and_aggregate_once(self):
        first = self.batch("FIRST", Decimal("3"), date(2030, 1, 1))
        last = self.batch("LAST", Decimal("5"), date(2031, 1, 1))
        movement = apply_manual_stock_change(
            tenant_id=self.tenant.id, outlet=self.outlet, menu_item=self.item,
            quantity_change=Decimal("-4"), reason=StockReason.WASTE, user=None,
        )
        self.balance.refresh_from_db()
        first.refresh_from_db()
        last.refresh_from_db()
        self.assertEqual(self.balance.quantity, Decimal("4"))
        self.assertEqual(first.remaining_quantity, Decimal("0"))
        self.assertEqual(last.remaining_quantity, Decimal("4"))
        self.assertEqual(movement.quantity_change, Decimal("-4"))

    def test_named_expired_batch_can_be_written_off_without_fefo_sale(self):
        old = self.batch("OLD", Decimal("4"), date(2026, 2, 1))
        self.batch("NEW", Decimal("4"), date(2030, 3, 1))
        movement = waste_batch_stock(
            tenant_id=self.tenant.id, batch_id=old.id,
            allowed_outlet_ids=[self.outlet.id],
            quantity=Decimal("2"), user=None, reason="Expired on shelf",
        )
        old.refresh_from_db()
        self.balance.refresh_from_db()
        self.assertEqual(old.remaining_quantity, Decimal("2"))
        self.assertEqual(self.balance.quantity, Decimal("6"))
        self.assertEqual(movement.reason, StockReason.WASTE)
        self.assertEqual(StockMovement.objects.filter(tenant=self.tenant).count(), 1)

    def test_legacy_stock_labeling_does_not_post_receipt_twice(self):
        batch = label_existing_stock_batch(
            tenant_id=self.tenant.id, outlet=self.outlet, menu_item=self.item,
            batch_code="LEGACY", quantity=Decimal("6"),
            received_at=date(2026, 1, 1),
            expiry_date=None, user=None,
        )
        self.balance.refresh_from_db()
        self.assertEqual(batch.remaining_quantity, Decimal("6"))
        self.assertEqual(self.balance.quantity, Decimal("8"))
        self.assertFalse(StockMovement.objects.filter(tenant=self.tenant).exists())
        with self.assertRaises(ValidationError):
            label_existing_stock_batch(
                tenant_id=self.tenant.id, outlet=self.outlet, menu_item=self.item,
                batch_code="TOO-MUCH", quantity=Decimal("3"),
                received_at=date(2026, 1, 1), expiry_date=None, user=None,
            )

    def test_hold_prevents_consumption_and_release_allows_it(self):
        first = self.batch("HELD", Decimal("8"), date(2030, 1, 1))
        change_batch_hold(
            tenant_id=self.tenant.id, batch_id=first.id,
            allowed_outlet_ids=[self.outlet.id],
            quarantined=True, user=None,
        )
        with self.assertRaises(ValidationError):
            apply_manual_stock_change(
                tenant_id=self.tenant.id, outlet=self.outlet,
                menu_item=self.item, quantity_change=Decimal("-1"),
                reason=StockReason.WASTE, user=None,
            )
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, Decimal("8"))
        change_batch_hold(
            tenant_id=self.tenant.id, batch_id=first.id,
            allowed_outlet_ids=[self.outlet.id],
            quarantined=False, user=None,
        )
        apply_manual_stock_change(
            tenant_id=self.tenant.id, outlet=self.outlet,
            menu_item=self.item, quantity_change=Decimal("-1"),
            reason=StockReason.WASTE, user=None,
        )
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, Decimal("7"))

    def test_exact_batch_allocation_is_linked_to_stock_movement(self):
        early = self.batch("EARLY", Decimal("3"), date(2030, 1, 1))
        later = self.batch("LATER", Decimal("5"), date(2031, 1, 1))
        movement = apply_manual_stock_change(
            tenant_id=self.tenant.pk, outlet=self.outlet, menu_item=self.item,
            quantity_change=Decimal("-4"), reason=StockReason.WASTE, user=None,
        )
        allocations = {
            row.batch_id: row.quantity
            for row in StockBatchAllocation.objects.filter(stock_movement=movement)
        }
        self.assertEqual(allocations, {
            early.pk: Decimal("3"), later.pk: Decimal("1"),
        })

    def test_recall_holds_matching_lot_without_discarding_or_changing_balances(self):
        matching = self.batch("RECALL-L1", Decimal("3"), date(2030, 1, 1))
        other = self.batch("RECALL-L2", Decimal("5"), date(2031, 1, 1))
        count = hold_matching_lot(
            tenant_id=self.tenant.pk, batch_id=matching.pk,
            allowed_outlet_ids=[self.outlet.pk],
            user=None, reason="Supplier safety notice",
        )
        matching.refresh_from_db()
        other.refresh_from_db()
        self.balance.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertTrue(matching.quarantined)
        self.assertFalse(other.quarantined)
        self.assertEqual(self.balance.quantity, Decimal("8"))
        self.assertEqual(matching.remaining_quantity, Decimal("3"))

    def test_manual_stock_rejects_invalid_quantity_without_posting(self):
        for invalid in (Decimal("NaN"), Decimal("Infinity"), Decimal("1.0005")):
            with self.subTest(invalid=str(invalid)):
                with self.assertRaises(ValidationError):
                    apply_manual_stock_change(
                        tenant_id=self.tenant.pk, outlet=self.outlet,
                        menu_item=self.item, quantity_change=invalid,
                        reason=StockReason.RECEIVE, user=None,
                    )
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, Decimal("8"))
        self.assertFalse(StockMovement.objects.exists())

    def test_manual_stock_rejects_cross_tenant_source_objects(self):
        other = Tenant.objects.create(name="Other Ledger", slug="other-ledger-scope")
        with self.assertRaises(ValidationError):
            apply_manual_stock_change(
                tenant_id=other.pk, outlet=self.outlet,
                menu_item=self.item, quantity_change=Decimal("1"),
                reason=StockReason.RECEIVE, user=None,
            )
        self.assertFalse(StockMovement.objects.exists())
