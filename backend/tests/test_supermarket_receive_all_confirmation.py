"""The one-click goods-receipt shortcut needs an explicit physical count confirmation."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance, StockMovement
from apps.purchasing.models import (
    PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, PurchaseReceipt, Supplier,
)
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Tenant, TenantSettings, Site, Outlet, OutletType


class SupermarketReceiveAllConfirmationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Checked Supplier Delivery", slug="checked-delivery-test")
        TenantSettings.objects.create(tenant=self.tenant, business_lines=["supermarket"], default_currency="UGX")
        site = Site.objects.create(tenant=self.tenant, name="Grocery")
        self.outlet = Outlet.objects.create(site=site, name="Stock room", outlet_type=OutletType.SUPERMARKET)
        self.user = User.objects.create_user(email="delivery-owner@example.test", password="TestPass9!")
        member = Membership.objects.create(user=self.user, tenant=self.tenant, role=MembershipRole.OWNER)
        member.sites.add(site)
        member.outlets.add(self.outlet)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Rice")
        self.item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Bag of rice",
            unit_price=Decimal("12000"), track_inventory=True,
        )
        supplier = Supplier.objects.create(tenant=self.tenant, name="Rice supplier")
        self.po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=supplier, outlet=self.outlet,
            status=PurchaseOrderStatus.SENT,
        )
        self.line = PurchaseOrderLine.objects.create(
            purchase_order=self.po, menu_item=self.item,
            quantity_ordered=Decimal("3"), unit_cost=Decimal("10000"),
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        self.url = reverse("staff-purchasing-order-detail", kwargs={"po_id": self.po.pk})

    def test_receive_all_requires_physical_check_without_stock_side_effect(self):
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="verified_physical_delivery"')
        self.assertContains(page, "I physically counted and accepted")
        response = self.client.post(self.url, {"action": "receive_all"})
        self.assertEqual(response.status_code, 302)
        self.line.refresh_from_db()
        self.assertEqual(self.line.quantity_received, Decimal("0"))
        self.assertFalse(PurchaseReceipt.objects.filter(purchase_order=self.po).exists())
        self.assertFalse(StockMovement.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(StockBalance.objects.filter(outlet=self.outlet, menu_item=self.item).exists())

    def test_confirmed_receive_all_records_a_single_receipt(self):
        self.assertEqual(
            self.client.post(
                self.url,
                {"action": "receive_all", "verified_physical_delivery": "yes"},
            ).status_code,
            302,
        )
        self.line.refresh_from_db()
        self.assertEqual(self.line.quantity_received, Decimal("3"))
        self.assertEqual(PurchaseReceipt.objects.filter(purchase_order=self.po).count(), 1)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("3"),
        )
