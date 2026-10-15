"""Explainable inventory planning calculations using recorded stock movements."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.batches import InventoryBatch
from apps.inventory.insights import build_stock_intelligence
from apps.inventory.models import StockBalance, StockMovement, StockReason
from apps.purchasing.models import (
    Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine,
)
from apps.tenants.models import Tenant, Site, Outlet, OutletType


class InventoryIntelligenceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Stock Insight", slug="stock-insight-test")
        site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(site=site, name="Retail", outlet_type=OutletType.RETAIL)
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Food")
        self.item = MenuItem.objects.create(
            tenant=self.tenant, category=cat, name="Pasta",
            unit_price=Decimal("3000"), track_inventory=True,
            reorder_level=Decimal("10"),
        )
        self.balance = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            quantity=Decimal("12"),
        )
        self.now = timezone.now()

    def insight(self, **options):
        return build_stock_intelligence(
            tenant=self.tenant, balances=[self.balance], at=self.now, **options,
        )[0]

    def test_rolling_usage_batch_aging_and_unbatched_stock(self):
        InventoryBatch.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            batch_code="RECENT", received_at=timezone.localdate()-timedelta(days=7),
            received_quantity=Decimal("8"), remaining_quantity=Decimal("8"),
        )
        StockMovement.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            reason=StockReason.SALE, quantity_change=Decimal("-6"),
        )
        row = self.insight()
        self.assertEqual(row["units_consumed_30d"], Decimal("6"))
        self.assertEqual(row["daily_usage"], Decimal("0.200"))
        self.assertEqual(row["days_cover"], Decimal("60.0"))
        self.assertEqual(row["age_0_30"], Decimal("8"))
        self.assertEqual(row["unbatched_qty"], Decimal("4"))
        self.assertEqual(row["suggested_order"], Decimal("0.000"))
        self.assertIsNone(row["lead_days"])
        self.assertFalse(row["inactive"])

    def test_known_dead_stock_requires_old_receipt_and_no_recent_usage(self):
        movement = StockMovement.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            reason=StockReason.RECEIVE, quantity_change=Decimal("12"),
        )
        StockMovement.objects.filter(pk=movement.pk).update(
            created_at=self.now-timedelta(days=120),
        )
        row = self.insight()
        self.assertTrue(row["inactive"])
        self.assertIsNone(row["days_cover"])

    def test_observed_supplier_delivery_lead_time(self):
        supplier = Supplier.objects.create(tenant=self.tenant, name="Supplier")
        po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=supplier, outlet=self.outlet,
        )
        PurchaseOrder.objects.filter(pk=po.pk).update(
            created_at=self.now-timedelta(days=10),
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=self.item, quantity_ordered=Decimal("12"),
        )
        receipt = PurchaseReceipt.objects.create(
            tenant=self.tenant, purchase_order=po,
        )
        PurchaseReceiptLine.objects.create(
            receipt=receipt, purchase_order_line=line,
            quantity_received=Decimal("12"),
        )
        row = self.insight(safety_days=4)
        self.assertEqual(row["lead_samples"], 1)
        self.assertGreater(row["lead_days"], Decimal("9"))
        self.assertLess(row["lead_days"], Decimal("11"))

    def test_rejects_cross_business_balances_and_invalid_buffer(self):
        other = Tenant.objects.create(name="Different", slug="different-stock-intelligence")
        with self.assertRaises(ValueError):
            build_stock_intelligence(tenant=other, balances=[self.balance])
        with self.assertRaises(ValueError):
            self.insight(safety_days=40)
