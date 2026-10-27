from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockMovement, StockReason
from apps.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    PurchaseReceipt,
    PurchaseReceiptLine,
    Supplier,
    SupplierProductCode,
    SupplierReturn,
)
from apps.purchasing.supplier_performance import supplier_performance_rows
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class SupplierPerformanceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Supplier performance",
            slug="supplier-performance",
        )
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["purchasing", "inventory"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Stock room",
            outlet_type=OutletType.SUPERMARKET,
        )
        category = MenuCategory.objects.create(tenant=self.tenant, name="General")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=category,
            name="Cooking oil",
            sku="OIL-PERF",
            unit_price=Decimal("5000"),
            track_inventory=True,
        )
        self.supplier = Supplier.objects.create(
            tenant=self.tenant,
            name="Reliable Supplies",
        )
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            code="REL-OIL",
            default_unit_cost=Decimal("1000"),
            is_preferred=True,
        )
        self.user = User.objects.create_user(
            email="supplier-performance@test.local",
            password="Password9!",
        )
        membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=MembershipRole.OWNER,
        )
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet)
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def _seed_evidence(self):
        now = timezone.now()
        today = timezone.localdate(now)

        delivered = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            outlet=self.outlet,
            status=PurchaseOrderStatus.RECEIVED,
            expected_date=today - timedelta(days=5),
            reference="PERF-DELIVERED",
            created_by=self.user,
        )
        PurchaseOrder.objects.filter(pk=delivered.pk).update(
            created_at=now - timedelta(days=10),
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=delivered,
            menu_item=self.item,
            quantity_ordered=Decimal("10"),
            quantity_received=Decimal("10"),
            unit_cost=Decimal("1000"),
        )

        first_receipt = PurchaseReceipt.objects.create(
            tenant=self.tenant,
            purchase_order=delivered,
            delivery_reference="PERF-R1",
            received_by=self.user,
        )
        PurchaseReceipt.objects.filter(pk=first_receipt.pk).update(
            created_at=now - timedelta(days=6),
        )
        first_line = PurchaseReceiptLine.objects.create(
            receipt=first_receipt,
            purchase_order_line=line,
            quantity_received=Decimal("5"),
            unit_cost_snapshot=Decimal("900"),
            landed_unit_cost_snapshot=Decimal("900"),
        )
        PurchaseReceiptLine.objects.filter(pk=first_line.pk).update(
            created_at=now - timedelta(days=6),
        )

        second_receipt = PurchaseReceipt.objects.create(
            tenant=self.tenant,
            purchase_order=delivered,
            delivery_reference="PERF-R2",
            received_by=self.user,
        )
        PurchaseReceipt.objects.filter(pk=second_receipt.pk).update(
            created_at=now - timedelta(days=4),
        )
        second_line = PurchaseReceiptLine.objects.create(
            receipt=second_receipt,
            purchase_order_line=line,
            quantity_received=Decimal("5"),
            unit_cost_snapshot=Decimal("1000"),
            landed_unit_cost_snapshot=Decimal("1000"),
        )
        PurchaseReceiptLine.objects.filter(pk=second_line.pk).update(
            created_at=now - timedelta(days=4),
        )

        overdue = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            outlet=self.outlet,
            status=PurchaseOrderStatus.SENT,
            expected_date=today - timedelta(days=3),
            reference="PERF-OVERDUE",
            created_by=self.user,
        )
        PurchaseOrder.objects.filter(pk=overdue.pk).update(
            created_at=now - timedelta(days=8),
        )
        PurchaseOrderLine.objects.create(
            purchase_order=overdue,
            menu_item=self.item,
            quantity_ordered=Decimal("10"),
            quantity_received=Decimal("0"),
            unit_cost=Decimal("1000"),
        )

        movement = StockMovement.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.item,
            quantity_change=Decimal("-1"),
            reason=StockReason.ADJUST_OUT,
            created_by=self.user,
            purchase_order=delivered,
            note="Supplier return",
        )
        SupplierReturn.objects.create(
            tenant=self.tenant,
            purchase_order=delivered,
            receipt_line=second_line,
            movement=movement,
            reference="RTV-PERF-1",
            quantity=Decimal("1"),
            note="Damaged container returned",
            returned_by=self.user,
        )

    def test_supplier_metrics_use_delivery_quantity_return_and_cost_evidence(self):
        self._seed_evidence()
        row = supplier_performance_rows(
            tenant=self.tenant,
            suppliers=[self.supplier],
            days=365,
        )[self.supplier.pk]
        self.assertEqual(row["mapped_products"], 1)
        self.assertEqual(row["preferred_products"], 1)
        self.assertEqual(row["purchase_orders"], 2)
        self.assertEqual(row["delivery_count"], 2)
        self.assertEqual(row["on_time_samples"], 2)
        self.assertEqual(row["on_time_percent"], Decimal("50.0"))
        self.assertEqual(row["quantity_fulfilled_percent"], Decimal("50.0"))
        self.assertEqual(row["return_rate_percent"], Decimal("10.0"))
        self.assertEqual(row["cost_increases"], 1)
        self.assertEqual(row["cost_decreases"], 0)
        self.assertEqual(row["cost_unchanged"], 0)
        self.assertGreater(row["average_lead_days"], Decimal("3.9"))
        self.assertLess(row["average_lead_days"], Decimal("4.1"))

    def test_supplier_directory_renders_evidence_based_performance(self):
        self._seed_evidence()
        response = self.client.get(
            reverse("staff-purchasing-suppliers"),
            {"days": "365"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reliable Supplies")
        self.assertContains(response, "50.0% on time")
        self.assertContains(response, "50.0% fulfilled")
        self.assertContains(response, "10.0% returned")
        self.assertContains(response, "↑ 1")
        self.assertContains(response, "No subjective overall score is assigned")
