"""Carton entry stays in inventory units and preserves PO packaging history."""
from decimal import Decimal
from types import SimpleNamespace
from django.test import TestCase
from django.urls import reverse
import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.catalog.packaging import to_stock_units
from apps.inventory.models import StockBalance, StockMovement, StockCountSession, StockCountStatus, StockTransferReceipt
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, PurchaseReceipt, Supplier
from apps.purchasing.serializers import PurchaseOrderCreateSerializer
from apps.purchasing.services import receive_purchase_order_goods
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY
from apps.tenants.models import Tenant, TenantSettings, Site, Outlet, OutletType


@pytest.mark.parametrize("units,cartons,factor,expected", [
    ("2", "3", 12, "38"), ("0", "2", 24, "48"), ("0.25", "1", 6, "6.25"),
])
def test_carton_conversion_exact(units, cartons, factor, expected):
    assert to_stock_units(units=units, cartons=cartons, units_per_carton=factor) == Decimal(expected)


@pytest.mark.parametrize("units,cartons,factor", [
    ("NaN", "1", 12), ("1.0001", "0", 12), ("-1", "1", 12),
    ("0", "1.2", 12), ("0", "1", 1), ("0", "100000000000000", 100),
    ("", "", 12), ("Infinity", "0", 12),
])
def test_carton_conversion_invalid(units, cartons, factor):
    with pytest.raises(ValidationError):
        to_stock_units(units=units, cartons=cartons, units_per_carton=factor)


class RetailCartonWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Carton Market", slug="carton-market")
        TenantSettings.objects.get_or_create(
            tenant=self.tenant,
            defaults={"business_lines": ["supermarket"], "default_currency": "UGX"},
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Warehouse")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Main shop", outlet_type=OutletType.SUPERMARKET,
        )
        self.destination = Outlet.objects.create(
            site=self.site, name="Second shop", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(
            email="carton-manager@example.test", password="TestPass9!",
        )
        self.member = Membership.objects.create(
            user=self.user, tenant=self.tenant, role=MembershipRole.OWNER,
        )
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Drinks")
        self.item = MenuItem.objects.create(
            tenant=self.tenant, category=self.category, name="Soda bottle",
            unit_price=Decimal("1000"), track_inventory=True, units_per_carton=12,
        )
        self.supplier = Supplier.objects.create(tenant=self.tenant, name="Drink wholesaler")
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def make_po(self, quantity="48", factor=12):
        po = PurchaseOrder.objects.create(
            tenant=self.tenant, outlet=self.outlet, supplier=self.supplier,
            status=PurchaseOrderStatus.SENT,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=self.item,
            quantity_ordered=Decimal(quantity), units_per_carton_snapshot=factor,
            unit_cost=Decimal("700"),
        )
        return po, line

    def test_receipt_uses_frozen_po_size_not_new_catalog_size(self):
        po, line = self.make_po()
        self.item.units_per_carton = 24
        self.item.save(update_fields=["units_per_carton"])
        url = reverse("staff-purchasing-order-detail", kwargs={"po_id": po.pk})
        self.assertContains(self.client.get(url), 'name="recv_cartons_')
        response = self.client.post(url, {
            "action": "receive", "delivery_reference": "CARTON-DELIVERY-1",
            f"recv_{line.id}": "2", f"recv_cartons_{line.id}": "2",
        })
        self.assertEqual(response.status_code, 302)
        line.refresh_from_db()
        self.assertEqual(line.quantity_received, Decimal("26"))
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("26"),
        )
        receipt = PurchaseReceipt.objects.get(purchase_order=po)
        self.assertEqual(receipt.lines.get().cartons_received, 2)
        self.assertEqual(receipt.lines.get().quantity_received, Decimal("26"))
        self.client.post(url, {
            "action": "receive", "delivery_reference": "carton-delivery-1",
            f"recv_{line.id}": "1",
        })
        self.assertEqual(PurchaseReceipt.objects.filter(purchase_order=po).count(), 1)

    def test_cartons_cannot_over_receive_and_mutate_stock(self):
        po, line = self.make_po(quantity="12")
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po, membership=self.member, user=self.user,
                lines_payload=[{"line_id": line.pk, "quantity": "1", "cartons": 1}],
            )
        self.assertFalse(PurchaseReceipt.objects.filter(purchase_order=po).exists())
        self.assertFalse(StockMovement.objects.filter(tenant=self.tenant).exists())

    def test_carton_transfer_records_exact_base_unit_balance(self):
        StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            quantity=Decimal("50"),
        )
        url = reverse("staff-inventory-transfer")
        self.assertContains(self.client.get(url), 'name="cartons"')
        response = self.client.post(url, {
            "from_outlet": self.outlet.pk, "to_outlet": self.destination.pk,
            "menu_item": self.item.pk, "quantity": "2", "cartons": "3",
            "note": "Checked cartons",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("12"),
        )
        self.assertFalse(
            StockBalance.objects.filter(outlet=self.destination, menu_item=self.item).exists(),
            "Dispatched cartons must not become available before physical receiving.",
        )
        receipt = StockTransferReceipt.objects.get(
            tenant=self.tenant, menu_item=self.item, to_outlet=self.destination,
        )
        self.assertEqual(receipt.dispatched_quantity, Decimal("38"))
        self.assertEqual(receipt.outstanding_quantity, Decimal("38"))

        receiver = User.objects.create_user(
            email="carton-receiver@example.test", password="TestPass9!",
        )
        receiving_role = Membership.objects.create(
            user=receiver, tenant=self.tenant, role=MembershipRole.STOREKEEPER,
        )
        receiving_role.sites.add(self.site)
        receiving_role.outlets.add(self.destination)
        self.client.force_login(receiver)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.destination.pk)
        session.save()
        confirm = self.client.post(
            reverse("staff-inventory-transfer-receipts"),
            {"action": "verify", "receipt_id": str(receipt.pk),
             "received_quantity": "38", "note": "Counted two pieces plus three cartons."},
        )
        self.assertEqual(confirm.status_code, 302)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "matched")
        self.assertEqual(receipt.outstanding_quantity, Decimal("0"))
        self.assertEqual(
            StockBalance.objects.get(outlet=self.destination, menu_item=self.item).quantity,
            Decimal("38"),
        )

    def test_existing_po_has_no_implicit_carton_setting(self):
        po, line = self.make_po(factor=1)
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po, membership=self.member, user=self.user,
                lines_payload=[{"line_id": line.pk, "cartons": 2}],
            )
        self.assertFalse(PurchaseReceipt.objects.filter(purchase_order=po).exists())

    def test_count_accepts_cartons_without_posting_stock(self):
        StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            quantity=Decimal("20"),
        )
        session = StockCountSession.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
        )
        url = reverse("staff-inventory-count-detail", kwargs={"session_id": session.pk})
        self.assertContains(self.client.get(url), 'name="cartons_')
        response = self.client.post(url, {
            "action": "submit", f"counted_{self.item.pk}": "3",
            f"cartons_{self.item.pk}": "2",
        })
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, StockCountStatus.REVIEW)
        self.assertEqual(session.lines.get().counted_quantity, Decimal("27"))
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("20"),
        )

    def test_purchase_order_serializer_snapshots_carton_size_and_cost(self):
        request = SimpleNamespace(
            tenant=self.tenant, tenant_membership=self.member, user=self.user,
        )
        ser = PurchaseOrderCreateSerializer(
            data={
                "supplier": str(self.supplier.pk), "outlet": str(self.outlet.pk),
                "lines": [{
                    "menu_item": str(self.item.pk), "cartons": 2,
                    "quantity_ordered": "1", "unit_cost": "700",
                }],
            },
            context={"request": request},
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        line = ser.save().lines.get()
        self.assertEqual(line.quantity_ordered, Decimal("25"))
        self.assertEqual(line.units_per_carton_snapshot, 12)
        self.assertEqual(line.unit_cost, Decimal("700"))

    def test_invalid_carton_transfer_does_not_write_stock(self):
        StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item,
            quantity=Decimal("50"),
        )
        self.client.post(reverse("staff-inventory-transfer"), {
            "from_outlet": self.outlet.pk, "to_outlet": self.destination.pk,
            "menu_item": self.item.pk, "quantity": "0", "cartons": "1.5",
        })
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("50"),
        )
        self.assertFalse(StockMovement.objects.filter(tenant=self.tenant).exists())
