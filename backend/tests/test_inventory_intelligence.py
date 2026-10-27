"""Explainable inventory planning calculations using recorded stock movements."""
from datetime import timedelta
from types import SimpleNamespace
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole
from apps.catalog.models import MenuCategory, MenuItem
from apps.console.forms import ConsoleMenuItemForm
from apps.inventory.batches import InventoryBatch
from apps.inventory.insights import build_stock_intelligence
from apps.inventory.models import StockBalance, StockMovement, StockReason
from apps.purchasing.models import (
    Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine,
    SupplierProductCode,
)
from apps.tenants.models import Tenant, TenantSettings, Site, Outlet, OutletType
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.staff.views_inventory import StaffStockBalanceListView


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


    def test_preferred_supplier_flows_into_planning_row_and_purchase_order_link(self):
        supplier = Supplier.objects.create(tenant=self.tenant, name="Preferred Foods")
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=supplier,
            menu_item=self.item,
            code="PASTA-PREF",
            default_unit_cost=Decimal("1800"),
            is_preferred=True,
        )
        row = self.insight()
        self.assertEqual(row["preferred_supplier_id"], supplier.pk)
        self.assertEqual(row["preferred_supplier"], "Preferred Foods")
        self.assertEqual(row["preferred_supplier_code"], "PASTA-PREF")
        self.assertEqual(row["preferred_supplier_cost"], Decimal("1800"))

        user = get_user_model().objects.create_user(
            email="planning-pref@test.local", password="Password9!",
        )
        membership = Membership.objects.create(
            tenant=self.tenant, user=user, role=MembershipRole.OWNER,
        )
        membership.outlets.add(self.outlet)
        membership.sites.add(self.outlet.site)
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session.save()
        response = self.client.get(reverse("staff-inventory-intelligence"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preferred Foods")
        self.assertContains(response, f"supplier={supplier.pk}")


class InventoryIntelligenceExportTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Planning Export", slug="planning-export")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["inventory", "purchasing"],
        )
        site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=site, name="Retail", outlet_type=OutletType.SUPERMARKET,
        )
        category = MenuCategory.objects.create(tenant=self.tenant, name="General")
        self.item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="=Unsafe product",
            unit_price=Decimal("1000"), track_inventory=True,
            reorder_level=Decimal("10"),
        )
        StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            quantity=Decimal("5"),
        )
        self.user = get_user_model().objects.create_user(
            email="planning-export@test.local", password="Password9!",
        )
        Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OWNER,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session.save()

    def test_filtered_csv_uses_same_planning_scope_and_escapes_text(self):
        response = self.client.get(
            reverse("staff-inventory-intelligence"),
            {"format": "csv", "low": "1", "safety_days": "4"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("text/csv", response["Content-Type"])
        body = response.content.decode("utf-8")
        self.assertIn("Suggested order", body)
        self.assertIn("'=Unsafe product", body)
        self.assertIn(",4\r\n", body)

    def test_low_stock_csv_filter_excludes_above_threshold_rows(self):
        StockBalance.objects.filter(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
        ).update(quantity=Decimal("12"))
        response = self.client.get(
            reverse("staff-inventory-intelligence"),
            {"format": "csv", "low": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Unsafe product", response.content.decode("utf-8"))



class InventoryCatalogueVisibilityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Retail Stock", slug="retail-stock-visibility")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "inventory"],
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Shop floor",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="General")

    def test_tracked_product_without_movement_gets_zero_balance(self):
        item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Geisha",
            unit_price=Decimal("3500"),
            track_inventory=True,
        )
        self.assertFalse(
            StockBalance.objects.filter(outlet=self.outlet, menu_item=item).exists()
        )

        view = StaffStockBalanceListView()
        view.request = SimpleNamespace(tenant=self.tenant)
        view._ensure_zero_balances_for_tracked_items(
            [self.outlet],
            [self.outlet.id],
        )

        balance = StockBalance.objects.get(outlet=self.outlet, menu_item=item)
        self.assertEqual(balance.quantity, Decimal("0"))

    def test_new_supermarket_product_defaults_to_inventory_tracking(self):
        form = ConsoleMenuItemForm(tenant=self.tenant)
        self.assertIs(form.fields["track_inventory"].initial, True)
