"""Multitenant branding regression: Fizo is a test tenant, never the platform identity."""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.pos.models import Order, Payment, PaymentMethod
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance, StockMovement, StockReason
from apps.purchasing.models import Supplier, PurchaseOrder
from apps.finance.models import FinanceCategory, FinanceCategoryKind, CashbookEntry
from django.utils import timezone
from decimal import Decimal
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

    def test_inventory_balances_and_movements_hide_foreign_tenant_stock(self):
        rows = []
        for tenant, outlet in self.tenants:
            category = MenuCategory.objects.create(tenant=tenant, name="Stock")
            item = MenuItem.objects.create(
                tenant=tenant, category=category, name=f"Private stock {tenant.slug}",
                unit_price=Decimal("1000"),
            )
            StockBalance.objects.create(
                tenant=tenant, outlet=outlet, menu_item=item, quantity=Decimal("12"),
            )
            StockMovement.objects.create(
                tenant=tenant, outlet=outlet, menu_item=item,
                quantity_change=Decimal("12"), reason=StockReason.RECEIVE,
                created_by=self.user, note=f"Private movement {tenant.slug}",
            )
            rows.append((tenant, outlet, item))
        for active, foreign in ((rows[0], rows[1]), (rows[1], rows[0])):
            with self.subTest(tenant=active[0].name):
                self._choose(active[0], active[1])
                balances = self.client.get(reverse("staff-inventory-balances"))
                self.assertEqual(balances.status_code, 200)
                self.assertContains(balances, active[2].name)
                self.assertNotContains(balances, foreign[2].name)
                movements = self.client.get(reverse("staff-inventory-movements"))
                self.assertEqual(movements.status_code, 200)
                self.assertContains(movements, active[2].name)
                self.assertNotContains(movements, foreign[2].name)

    def test_finance_cashbook_html_and_csv_exclude_foreign_tenant(self):
        for tenant, outlet in self.tenants:
            category = FinanceCategory.objects.create(
                tenant=tenant, name=f"Cashbook {tenant.slug}",
                kind=FinanceCategoryKind.INCOME,
            )
            CashbookEntry.objects.create(
                tenant=tenant, category=category,
                site=outlet.site, amount=Decimal("1200"),
                transaction_date=timezone.localdate(),
                reference=f"REF-{tenant.slug}", created_by=self.user,
            )
        for tenant, outlet in self.tenants:
            with self.subTest(tenant=tenant.name):
                self._choose(tenant, outlet)
                foreign = next(t for t, _ in self.tenants if t.pk != tenant.pk)
                for query in ({}, {"format": "csv"}):
                    response = self.client.get(reverse("staff-finance-entries"), query)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, f"REF-{tenant.slug}")
                    self.assertNotContains(response, f"REF-{foreign.slug}")

    def test_foreign_tenant_payment_cannot_be_viewed_or_refunded_through_order(self):
        first, second = self.tenants
        foreign_order = Order.objects.create(
            tenant=second[0], outlet=second[1], created_by=self.user,
            currency="UGX", bill_reference="PRIVATE-PAID-ORDER",
            subtotal=Decimal("5000"), total=Decimal("5000"),
        )
        payment = Payment.objects.create(
            tenant=second[0], order=foreign_order, amount=Decimal("5000"),
            method=PaymentMethod.CASH, idempotency_key="private-payment-test",
            recorded_by=self.user,
        )
        self._choose(*first)
        url = reverse("staff-order-detail", kwargs={"order_id": foreign_order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        for action in ("record_payment", "record_refund"):
            with self.subTest(action=action):
                response = self.client.post(url, {
                    "action": action, "amount": "1000", "payment_id": str(payment.pk),
                    "reason": "Cross-tenant test",
                    "idempotency_key": f"blocked-{action}",
                })
                self.assertEqual(response.status_code, 404)
        self.assertEqual(Payment.objects.filter(order=foreign_order).count(), 1)
        self.assertEqual(foreign_order.refunds.count(), 0)

    def test_purchasing_lists_and_details_never_expose_other_tenants(self):
        purchases = []
        for tenant, outlet in self.tenants:
            supplier = Supplier.objects.create(
                tenant=tenant, name=f"Supplier for {tenant.slug}",
            )
            purchase = PurchaseOrder.objects.create(
                tenant=tenant, outlet=outlet, supplier=supplier,
                reference=f"PO-{tenant.slug}", created_by=self.user,
            )
            purchases.append((tenant, outlet, supplier, purchase))
        for active, foreign in ((purchases[0], purchases[1]), (purchases[1], purchases[0])):
            with self.subTest(active_tenant=active[0].name):
                self._choose(active[0], active[1])
                supplier_page = self.client.get(reverse("staff-purchasing-suppliers"))
                self.assertEqual(supplier_page.status_code, 200)
                self.assertContains(supplier_page, active[2].name)
                self.assertNotContains(supplier_page, foreign[2].name)
                order_page = self.client.get(reverse("staff-purchasing-orders"))
                self.assertEqual(order_page.status_code, 200)
                self.assertContains(order_page, active[3].reference)
                self.assertNotContains(order_page, foreign[3].reference)
                detail = self.client.get(reverse(
                    "staff-purchasing-order-detail", kwargs={"po_id": foreign[3].pk}
                ))
                self.assertEqual(detail.status_code, 404)

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
