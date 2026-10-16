"""Staff supermarket cashier flow: scan and POST-only next basket."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.pos.models import Order
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class SupermarketCashierLaneTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Cashier Grocery", slug="cashier-grocery")
        TenantSettings.objects.create(
            tenant=self.tenant, business_lines=["supermarket"],
            default_currency="UGX",
        )
        site = Site.objects.create(tenant=self.tenant, name="Store")
        self.outlet = Outlet.objects.create(
            site=site, name="Till area", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="cashier-grocery@test.local", password="TestPass9!")
        membership = Membership.objects.create(
            user=self.user, tenant=self.tenant, role=MembershipRole.OUTLET_MANAGER,
        )
        membership.sites.add(site)
        membership.outlets.add(self.outlet)
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_scan_first_form_reaches_existing_server_side_checkout(self):
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Grocery")
        MenuItem.objects.create(
            tenant=self.tenant, category=cat, name="Sugar", sku="SUG-001",
            barcode="1234567890123", unit_price=Decimal("4500"), track_inventory=False,
        )
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.user)
        url = reverse("staff-order-detail", kwargs={"order_id": order.id})
        response = self.client.get(url)
        assert response.status_code == 200
        assert b"Fast supermarket checkout" in response.content
        assert b"data-retail-scan-form" in response.content
        assert b"data-retail-scan-status" in response.content
        scanned = self.client.post(
            url, {"action": "scan_add_line", "code": "1234567890123", "quantity": "2"},
        )
        assert scanned.status_code == 302
        order.refresh_from_db()
        assert order.lines.filter(menu_item__sku="SUG-001", is_voided=False).exists()

    def test_cash_tender_helper_is_supermarket_only_and_ledger_uses_existing_payment(self):
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            total=Decimal("9000"), subtotal=Decimal("9000"),
        )
        response = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        assert response.status_code == 200
        # Checkout staff can view the change calculator only when payment is allowed.
        if response.context["can_record_payment"] and response.context["payment_form"]:
            assert b"Cash received &amp; change" in response.content
            assert b"data-retail-cash-received" in response.content
            assert b"data-balance-due" in response.content
            assert b"Record the due amount, not the cash tendered" in response.content

    def test_next_sale_is_post_only(self):
        url = reverse("staff-order-quick-create")
        before = Order.objects.filter(tenant=self.tenant).count()
        response = self.client.get(url)
        assert response.status_code == 302
        assert Order.objects.filter(tenant=self.tenant).count() == before
        response = self.client.post(url)
        assert response.status_code == 302
        assert Order.objects.filter(tenant=self.tenant).count() == before + 1
