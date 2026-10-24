"""Multitenant branding regression: Fizo is a test tenant, never the platform identity."""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.pos.models import Order
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class SharedTenantBrandingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="branding@test.local", password="TestPass9!")
        self.tenants = []
        for name, slug in (("Fizo", "fizo-brand-test"), ("Green Valley Market", "green-valley-brand-test")):
            tenant = Tenant.objects.create(name=name, slug=slug)
            TenantSettings.objects.create(tenant=tenant, business_lines=["supermarket"], default_currency="UGX")
            site = Site.objects.create(tenant=tenant, name="Main site")
            outlet = Outlet.objects.create(site=site, name="Till 1", outlet_type=OutletType.SUPERMARKET)
            membership = Membership.objects.create(user=self.user, tenant=tenant, role=MembershipRole.OWNER)
            membership.sites.add(site)
            membership.outlets.add(outlet)
            self.tenants.append((tenant, outlet))
        self.client.force_login(self.user)

    def _choose(self, tenant, outlet):
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(outlet.pk)
        session.save()

    def test_sales_history_is_scoped_to_selected_tenant(self):
        first, second = self.tenants
        first_order = Order.objects.create(
            tenant=first[0], outlet=first[1], created_by=self.user, currency="UGX",
            bill_reference="TEST-FIRST-ONLY",
        )
        second_order = Order.objects.create(
            tenant=second[0], outlet=second[1], created_by=self.user, currency="UGX",
            bill_reference="TEST-SECOND-ONLY",
        )
        for active, other_order, own_reference, foreign_reference in (
            (first, second_order, first_order.bill_reference, second_order.bill_reference),
            (second, first_order, second_order.bill_reference, first_order.bill_reference),
        ):
            with self.subTest(active_tenant=active[0].name):
                self._choose(*active)
                history = self.client.get(reverse("staff-orders"))
                self.assertEqual(history.status_code, 200)
                self.assertContains(history, own_reference)
                self.assertNotContains(history, foreign_reference)
                foreign_detail = self.client.get(reverse(
                    "staff-order-detail", kwargs={"order_id": other_order.id}
                ))
                self.assertEqual(foreign_detail.status_code, 404)

    def test_org_console_brand_uses_active_tenant_after_switch(self):
        for tenant, outlet in reversed(self.tenants):
            with self.subTest(tenant=tenant.name):
                self._choose(tenant, outlet)
                response = self.client.get(reverse("console-org"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, tenant.name)
                if tenant.name != "Fizo":
                    self.assertNotContains(response, ">Fizo</a>")
                    self.assertNotContains(response, "Fizo business")

    def test_inventory_balances_label_is_current_tenant(self):
        for tenant, outlet in reversed(self.tenants):
            with self.subTest(tenant=tenant.name):
                self._choose(tenant, outlet)
                response = self.client.get(reverse("staff-inventory-balances"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, tenant.name)
                if tenant.name != "Fizo":
                    self.assertNotContains(response, "Fizo / Supermarket / Inventory")
