"""Explainable inventory planning calculations using recorded stock movements."""
from datetime import timedelta
import uuid
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
from apps.inventory.insights import (
    build_stock_intelligence,
    build_warehouse_replenishment_proposals,
)
from apps.inventory.models import (
    StockBalance, StockMovement, StockReason,
    StockTransferRequest, StockTransferRequestStatus,
)
from apps.purchasing.models import (
    Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine,
    SupplierProductCode,
)
from apps.tenants.models import Tenant, TenantSettings, Site, Outlet, OutletType
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY,
)
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



class WarehouseReplenishmentPlanningTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Warehouse Planning",
            slug="warehouse-planning",
        )
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["inventory", "purchasing", "pos"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.branch_a = Outlet.objects.create(
            site=self.site, name="Branch A", outlet_type=OutletType.SUPERMARKET,
        )
        self.branch_b = Outlet.objects.create(
            site=self.site, name="Branch B", outlet_type=OutletType.RETAIL,
        )
        self.warehouse = Outlet.objects.create(
            site=self.site, name="Central warehouse", outlet_type=OutletType.WAREHOUSE,
        )
        category = MenuCategory.objects.create(
            tenant=self.tenant, name="General",
        )
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=category,
            name="Replenishment soap",
            sku="REPL-SOAP",
            unit_price=Decimal("5000"),
            track_inventory=True,
            reorder_level=Decimal("10"),
        )
        self.branch_a_balance = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.branch_a, menu_item=self.item,
            quantity=Decimal("2"),
        )
        self.branch_b_balance = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.branch_b, menu_item=self.item,
            quantity=Decimal("2"),
        )
        self.warehouse_balance = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.warehouse, menu_item=self.item,
            quantity=Decimal("10"),
        )

    def _planning_rows(self):
        return build_stock_intelligence(
            tenant=self.tenant,
            balances=[self.branch_a_balance, self.branch_b_balance],
            safety_days=3,
        )

    def test_proposals_never_double_allocate_warehouse_stock(self):
        proposals = build_warehouse_replenishment_proposals(
            tenant=self.tenant,
            planning_rows=self._planning_rows(),
            warehouse_balances=[self.warehouse_balance],
        )
        self.assertEqual(len(proposals), 2)
        self.assertEqual(proposals[0]["proposed_quantity"], Decimal("8.000"))
        self.assertEqual(proposals[1]["proposed_quantity"], Decimal("2.000"))
        self.assertEqual(
            sum((row["proposed_quantity"] for row in proposals), Decimal("0")),
            Decimal("10.000"),
        )

    def test_open_inbound_and_approved_source_commitments_reduce_proposals(self):
        StockTransferRequest.objects.create(
            tenant=self.tenant,
            from_outlet=self.warehouse,
            to_outlet=self.branch_a,
            menu_item=self.item,
            requested_quantity=Decimal("5"),
            status=StockTransferRequestStatus.PENDING,
        )
        other_site = Site.objects.create(tenant=self.tenant, name="Other")
        other_branch = Outlet.objects.create(
            site=other_site, name="Other branch", outlet_type=OutletType.SUPERMARKET,
        )
        StockTransferRequest.objects.create(
            tenant=self.tenant,
            from_outlet=self.warehouse,
            to_outlet=other_branch,
            menu_item=self.item,
            requested_quantity=Decimal("4"),
            approved_quantity=Decimal("4"),
            status=StockTransferRequestStatus.APPROVED,
        )

        proposals = build_warehouse_replenishment_proposals(
            tenant=self.tenant,
            planning_rows=self._planning_rows(),
            warehouse_balances=[self.warehouse_balance],
        )
        by_branch = {row["to_outlet_id"]: row for row in proposals}
        self.assertEqual(
            by_branch[self.branch_a.pk]["open_inbound"], Decimal("5.000")
        )
        self.assertEqual(
            by_branch[self.branch_a.pk]["proposed_quantity"], Decimal("3.000")
        )
        self.assertEqual(
            by_branch[self.branch_b.pk]["proposed_quantity"], Decimal("3.000")
        )
        self.assertEqual(
            sum((row["proposed_quantity"] for row in proposals), Decimal("0")),
            Decimal("6.000"),
        )

    def test_fully_received_dispatched_transfer_is_not_counted_as_open_inbound(self):
        from apps.inventory.models import StockTransferReceipt

        receipt = StockTransferReceipt.objects.create(
            tenant=self.tenant,
            transfer_batch=uuid.uuid4(),
            from_outlet=self.warehouse,
            to_outlet=self.branch_a,
            menu_item=self.item,
            dispatched_quantity=Decimal("5"),
            posted_quantity=Decimal("5"),
            received_quantity=Decimal("5"),
            status="matched",
        )
        StockTransferRequest.objects.create(
            tenant=self.tenant,
            from_outlet=self.warehouse,
            to_outlet=self.branch_a,
            menu_item=self.item,
            requested_quantity=Decimal("5"),
            approved_quantity=Decimal("5"),
            status=StockTransferRequestStatus.DISPATCHED,
            transfer_receipt=receipt,
        )
        # Reflect the completed receipt in destination on-hand stock.
        self.branch_a_balance.quantity = Decimal("7")
        self.branch_a_balance.save(update_fields=["quantity", "updated_at"])

        rows = build_stock_intelligence(
            tenant=self.tenant,
            balances=[self.branch_a_balance],
            safety_days=3,
        )
        proposals = build_warehouse_replenishment_proposals(
            tenant=self.tenant,
            planning_rows=rows,
            warehouse_balances=[self.warehouse_balance],
        )
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["open_inbound"], Decimal("0.000"))
        self.assertEqual(proposals[0]["proposed_quantity"], Decimal("3.000"))

    def test_stock_planning_ui_creates_pending_request_without_moving_stock(self):
        user = get_user_model().objects.create_user(
            email="warehouse-planning@test.local",
            password="Password9!",
        )
        membership = Membership.objects.create(
            tenant=self.tenant, user=user, role=MembershipRole.OWNER,
        )
        membership.sites.add(self.site)
        membership.outlets.add(self.branch_a, self.warehouse)
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.branch_a.pk)
        session.save()

        page = self.client.get(reverse("staff-inventory-intelligence"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Warehouse stock can cover")
        self.assertContains(page, "Central warehouse")
        self.assertContains(page, "Request from warehouse")

        before_branch = self.branch_a_balance.quantity
        before_warehouse = self.warehouse_balance.quantity
        response = self.client.post(
            reverse("staff-inventory-intelligence"),
            {
                "from_outlet": str(self.warehouse.pk),
                "to_outlet": str(self.branch_a.pk),
                "menu_item": str(self.item.pk),
                "safety_days": "3",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("staff-inventory-transfer-requests"))

        request_row = StockTransferRequest.objects.get(
            tenant=self.tenant,
            from_outlet=self.warehouse,
            to_outlet=self.branch_a,
            menu_item=self.item,
        )
        self.assertEqual(request_row.status, StockTransferRequestStatus.PENDING)
        self.assertEqual(request_row.requested_quantity, Decimal("8.000"))

        self.branch_a_balance.refresh_from_db()
        self.warehouse_balance.refresh_from_db()
        self.assertEqual(self.branch_a_balance.quantity, before_branch)
        self.assertEqual(self.warehouse_balance.quantity, before_warehouse)
        self.assertFalse(
            StockMovement.objects.filter(
                tenant=self.tenant,
                menu_item=self.item,
                reason__in=[StockReason.TRANSFER_OUT, StockReason.TRANSFER_IN],
            ).exists()
        )
