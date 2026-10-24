"""Currency integrity across new tenants and safe legacy-basket repair."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.pos.models import Order, OrderLine, Payment
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class OrderCurrencyRepairTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Currency Test Store", slug="currency-test-store")
        TenantSettings.objects.create(tenant=self.tenant, default_currency="UGX")
        self.site = Site.objects.create(tenant=self.tenant, name="Store")
        self.outlet = Outlet.objects.create(site=self.site, name="Till", outlet_type=OutletType.SUPERMARKET)

    def test_new_orders_always_use_tenant_currency(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet)
        self.assertEqual(order.currency, "UGX")
        explicit_wrong = Order.objects.create(tenant=self.tenant, outlet=self.outlet, currency="USD")
        self.assertEqual(explicit_wrong.currency, "UGX")

    def test_repair_dry_run_and_safe_apply(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet)
        Order.objects.filter(pk=order.pk).update(currency="USD")
        output = StringIO()
        call_command("reconcile_open_order_currency", stdout=output)
        order.refresh_from_db()
        self.assertEqual(order.currency, "USD")
        self.assertIn("Preview only", output.getvalue())
        call_command("reconcile_open_order_currency", "--apply", stdout=StringIO())
        order.refresh_from_db()
        self.assertEqual(order.currency, "UGX")

    def test_closed_orders_preserve_original_currency(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet)
        Order.objects.filter(pk=order.pk).update(currency="USD", status="closed")
        call_command("reconcile_open_order_currency", "--apply", stdout=StringIO())
        order.refresh_from_db()
        self.assertEqual(order.currency, "USD")

    def test_nonempty_baskets_need_explicit_opt_in(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet)
        OrderLine.objects.create(order=order, label="Soap", quantity=1, unit_price=1000, line_total=1000)
        Order.objects.filter(pk=order.pk).update(currency="USD")
        call_command("reconcile_open_order_currency", "--apply", stdout=StringIO())
        order.refresh_from_db()
        self.assertEqual(order.currency, "USD")
        call_command("reconcile_open_order_currency", "--apply", "--include-lines", stdout=StringIO())
        order.refresh_from_db()
        self.assertEqual(order.currency, "UGX")
