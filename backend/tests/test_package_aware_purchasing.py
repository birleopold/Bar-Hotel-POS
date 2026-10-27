from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, ProductPackage
from apps.inventory.models import StockBalance
from apps.inventory.services import validate_and_consume_stock_for_paid_order
from apps.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    PurchaseReceiptLine,
    Supplier,
)
from apps.purchasing.services import receive_purchase_order_goods
from apps.pos.models import Order
from apps.pos.services.orders import add_line_to_open_order
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class PackageAwarePurchasingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Package purchasing", slug="package-purchasing")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["purchasing", "inventory", "pos"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main store")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Stock room", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(
            email="package-purchasing@test.local", password="Password9!",
        )
        member = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OWNER,
        )
        member.sites.add(self.site)
        member.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Drinks")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Mineral water 500ml",
            sku="WATER-500",
            unit_price=Decimal("1000"),
            track_inventory=True,
        )
        self.package = ProductPackage.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            name="Case of 24",
            units_per_package=Decimal("24"),
            barcode="WATER-CASE-24",
            sku_alias="WATER24",
            is_purchasable=True,
            is_sellable=True,
        )
        self.supplier = Supplier.objects.create(tenant=self.tenant, name="Water supplier")
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_purchase_order_ui_exposes_configured_packages(self):
        response = self.client.get(reverse("staff-purchasing-order-create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configured package")
        self.assertContains(response, "Case of 24")
        self.assertContains(response, "24.000 base units")
        self.assertContains(response, 'name="line_0_package_count"')

    def test_package_order_snapshots_base_units_and_receiving_posts_base_stock(self):
        create = self.client.post(
            reverse("staff-purchasing-order-create"),
            {
                "supplier": str(self.supplier.pk),
                "outlet": str(self.outlet.pk),
                "reference": "PO-PACK-001",
                "expected_date": "",
                "notes": "",
                "line_0_menu_item": str(self.item.pk),
                "line_0_quantity_ordered": "",
                "line_0_product_package": str(self.package.pk),
                "line_0_package_count": "10",
                "line_0_cartons": "",
                "line_0_unit_cost": "800",
            },
        )
        self.assertEqual(create.status_code, 302)
        po = PurchaseOrder.objects.get(reference="PO-PACK-001")
        line = po.lines.get()
        self.assertEqual(line.quantity_ordered, Decimal("240"))
        self.assertEqual(line.package_quantity_ordered, 10)
        self.assertEqual(line.package_name_snapshot, "Case of 24")
        self.assertEqual(line.package_units_snapshot, Decimal("24"))
        self.assertEqual(line.product_package, self.package)

        detail_url = reverse("staff-purchasing-order-detail", kwargs={"po_id": po.pk})
        sent = self.client.post(detail_url, {"action": "send"})
        self.assertEqual(sent.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrderStatus.SENT)

        detail = self.client.get(detail_url)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "10 × Case of 24")
        self.assertContains(detail, 'name="recv_packages_')
        self.assertContains(detail, "24.000 each")

        received = self.client.post(
            detail_url,
            {
                "action": "receive",
                f"recv_{line.pk}": "",
                f"recv_packages_{line.pk}": "4",
                f"recv_cartons_{line.pk}": "",
                f"batch_{line.pk}": "",
                f"expiry_{line.pk}": "",
                "delivery_reference": "DN-PACK-001",
                "receipt_note": "Four cases physically counted",
                "discrepancy_note": "",
            },
        )
        self.assertEqual(received.status_code, 302)
        line.refresh_from_db()
        po.refresh_from_db()
        self.assertEqual(line.quantity_received, Decimal("96"))
        self.assertEqual(line.quantity_remaining, Decimal("144"))
        self.assertEqual(po.status, PurchaseOrderStatus.PARTIALLY_RECEIVED)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("96"),
        )
        receipt_line = PurchaseReceiptLine.objects.get(receipt__purchase_order=po)
        self.assertEqual(receipt_line.packages_received, 4)
        self.assertEqual(receipt_line.quantity_received, Decimal("96"))

    def test_service_rejects_fractional_package_count_without_stock_side_effect(self):
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            outlet=self.outlet,
            status=PurchaseOrderStatus.SENT,
            created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            menu_item=self.item,
            quantity_ordered=Decimal("48"),
            unit_cost=Decimal("800"),
            product_package=self.package,
            package_name_snapshot="Case of 24",
            package_units_snapshot=Decimal("24"),
            package_quantity_ordered=2,
        )
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po,
                lines_payload=[{"line_id": line.pk, "packages": "1.5", "quantity": "0"}],
                user=self.user,
                membership=membership,
                delivery_reference="DN-FRACTIONAL",
            )
        line.refresh_from_db()
        self.assertEqual(line.quantity_received, Decimal("0"))
        self.assertFalse(StockBalance.objects.filter(outlet=self.outlet, menu_item=self.item).exists())

    def test_package_snapshot_survives_later_package_edit(self):
        create = self.client.post(
            reverse("staff-purchasing-order-create"),
            {
                "supplier": str(self.supplier.pk),
                "outlet": str(self.outlet.pk),
                "reference": "PO-PACK-SNAPSHOT",
                "line_0_menu_item": str(self.item.pk),
                "line_0_product_package": str(self.package.pk),
                "line_0_package_count": "2",
                "line_0_unit_cost": "800",
            },
        )
        self.assertEqual(create.status_code, 302)
        line = PurchaseOrder.objects.get(reference="PO-PACK-SNAPSHOT").lines.get()
        ProductPackage.objects.filter(pk=self.package.pk).update(
            name="Case renamed",
            units_per_package=Decimal("30"),
        )
        line.refresh_from_db()
        self.assertEqual(line.package_name_snapshot, "Case of 24")
        self.assertEqual(line.package_units_snapshot, Decimal("24"))
        self.assertEqual(line.quantity_ordered, Decimal("48"))

    def test_package_for_other_product_is_rejected_without_po(self):
        other = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Juice",
            sku="JUICE",
            unit_price=Decimal("2000"),
            track_inventory=True,
        )
        response = self.client.post(
            reverse("staff-purchasing-order-create"),
            {
                "supplier": str(self.supplier.pk),
                "outlet": str(self.outlet.pk),
                "reference": "PO-BAD-PACK",
                "line_0_menu_item": str(other.pk),
                "line_0_product_package": str(self.package.pk),
                "line_0_package_count": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose an active purchasable package")
        self.assertFalse(PurchaseOrder.objects.filter(reference="PO-BAD-PACK").exists())

    def _receive_costed_po(self, *, reference, quantity, unit_cost):
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            outlet=self.outlet,
            status=PurchaseOrderStatus.SENT,
            reference=reference,
            created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            menu_item=self.item,
            quantity_ordered=Decimal(str(quantity)),
            unit_cost=Decimal(str(unit_cost)) if unit_cost is not None else None,
        )
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        receive_purchase_order_goods(
            po=po,
            lines_payload=[{"line_id": line.pk, "quantity": str(quantity)}],
            user=self.user,
            membership=membership,
            delivery_reference="DN-" + reference,
        )
        return po, line

    def test_receipts_build_outlet_weighted_average_cost_and_snapshot_evidence(self):
        first_po, first_line = self._receive_costed_po(
            reference="COST-001", quantity="10", unit_cost="800",
        )
        balance = StockBalance.objects.get(outlet=self.outlet, menu_item=self.item)
        self.assertEqual(balance.quantity, Decimal("10"))
        self.assertEqual(balance.average_unit_cost, Decimal("800.0000"))
        self.assertTrue(balance.cost_basis_complete)
        first_receipt = PurchaseReceiptLine.objects.get(
            purchase_order_line=first_line,
        )
        self.assertEqual(first_receipt.unit_cost_snapshot, Decimal("800.00"))

        second_po, second_line = self._receive_costed_po(
            reference="COST-002", quantity="10", unit_cost="1000",
        )
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("20"))
        self.assertEqual(balance.average_unit_cost, Decimal("900.0000"))
        self.assertTrue(balance.cost_basis_complete)
        self.assertEqual(
            PurchaseReceiptLine.objects.get(
                purchase_order_line=second_line,
            ).unit_cost_snapshot,
            Decimal("1000.00"),
        )

    def test_new_receipt_does_not_fake_cost_for_legacy_uncosted_stock(self):
        StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.item,
            quantity=Decimal("5"),
            average_unit_cost=None,
            cost_basis_complete=False,
        )
        self._receive_costed_po(
            reference="COST-LEGACY", quantity="5", unit_cost="1000",
        )
        balance = StockBalance.objects.get(outlet=self.outlet, menu_item=self.item)
        self.assertEqual(balance.quantity, Decimal("10"))
        self.assertIsNone(balance.average_unit_cost)
        self.assertFalse(balance.cost_basis_complete)

    def test_sale_freezes_authoritative_cost_snapshot_before_stock_moves(self):
        self._receive_costed_po(
            reference="COST-SALE", quantity="10", unit_cost="750",
        )
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            currency="UGX",
        )
        line = add_line_to_open_order(
            order=order,
            menu_item=self.item,
            quantity=Decimal("2"),
            user=self.user,
        )
        validate_and_consume_stock_for_paid_order(order, self.user)
        line.refresh_from_db()
        balance = StockBalance.objects.get(outlet=self.outlet, menu_item=self.item)
        self.assertEqual(line.cost_unit_snapshot, Decimal("750.0000"))
        self.assertTrue(line.cost_basis_complete_snapshot)
        self.assertEqual(balance.quantity, Decimal("8"))
        self.assertEqual(balance.average_unit_cost, Decimal("750.0000"))
        self.assertTrue(balance.cost_basis_complete)

