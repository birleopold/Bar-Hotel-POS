from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance
from apps.pos.models import (
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    Refund,
    SupermarketLineReturn,
)
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.staff.profitability import build_merchandise_profitability
from apps.staff.report_csv import format_sales_summary_csv
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class SalesProfitabilityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Profitability Test",
            slug="profitability-test",
        )
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["sales", "inventory", "pos"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Primary store",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.other_outlet = Outlet.objects.create(
            site=self.site,
            name="Other store",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(
            email="profitability@test.local",
            password="Password9!",
        )
        membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=MembershipRole.OWNER,
        )
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet, self.other_outlet)

        self.category = MenuCategory.objects.create(
            tenant=self.tenant,
            name="General",
        )
        self.known_item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Known cost soap",
            sku="KNOWN-SOAP",
            unit_price=Decimal("100.00"),
            track_inventory=True,
        )
        self.unknown_item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Unknown cost oil",
            sku="UNKNOWN-OIL",
            unit_price=Decimal("50.00"),
            track_inventory=True,
        )
        self.today = date.today()

    def _paid_order(
        self,
        *,
        outlet,
        item,
        price,
        cost,
        trusted,
        key,
    ):
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=outlet,
            status=OrderStatus.CLOSED,
            subtotal=Decimal(str(price)),
            tax_total=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal(str(price)),
            is_paid=True,
            created_by=self.user,
        )
        line = OrderLine.objects.create(
            order=order,
            menu_item=item,
            label=item.name,
            quantity=Decimal("1"),
            unit_price=Decimal(str(price)),
            line_total=Decimal(str(price)),
            cost_unit_snapshot=(Decimal(str(cost)) if cost is not None else None),
            cost_basis_complete_snapshot=trusted,
        )
        payment = Payment.objects.create(
            tenant=self.tenant,
            order=order,
            amount=Decimal(str(price)),
            method="cash",
            idempotency_key=key,
            recorded_by=self.user,
        )
        return order, line, payment

    def test_historical_cost_and_restocked_return_use_original_sale_cost(self):
        order, line, payment = self._paid_order(
            outlet=self.outlet,
            item=self.known_item,
            price="100.00",
            cost="60.00",
            trusted=True,
            key="profit-known",
        )
        # Later stock cost must not rewrite historical sale profitability.
        StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.known_item,
            quantity=Decimal("10"),
            average_unit_cost=Decimal("9999.0000"),
            cost_basis_complete=True,
        )
        refund = Refund.objects.create(
            tenant=self.tenant,
            order=order,
            payment=payment,
            amount=Decimal("50.00"),
            reason="Half quantity returned",
            idempotency_key="profit-refund",
            recorded_by=self.user,
            restocked=True,
        )
        SupermarketLineReturn.objects.create(
            refund=refund,
            tenant=self.tenant,
            order=order,
            order_line=line,
            quantity=Decimal("0.5"),
            reason="Half quantity returned",
            restocked=True,
            created_by=self.user,
            idempotency_key="profit-line-return",
        )

        result = build_merchandise_profitability(
            tenant_id=self.tenant.pk,
            date_from=self.today,
            date_to=self.today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertEqual(result["sale_revenue"], Decimal("100.00"))
        self.assertEqual(result["return_revenue"], Decimal("50.00"))
        self.assertEqual(result["net_merchandise_revenue"], Decimal("50.00"))
        self.assertEqual(result["known_net_cogs"], Decimal("30.00"))
        self.assertEqual(result["known_gross_profit"], Decimal("20.00"))
        self.assertEqual(result["known_margin_percent"], Decimal("40.0"))
        self.assertEqual(result["cost_coverage_percent"], Decimal("100.0"))
        self.assertTrue(result["profitability_complete"])

    def test_unknown_sale_cost_reduces_coverage_and_is_not_treated_as_zero(self):
        self._paid_order(
            outlet=self.outlet,
            item=self.known_item,
            price="100.00",
            cost="60.00",
            trusted=True,
            key="profit-known-coverage",
        )
        self._paid_order(
            outlet=self.outlet,
            item=self.unknown_item,
            price="50.00",
            cost=None,
            trusted=False,
            key="profit-unknown-coverage",
        )

        result = build_merchandise_profitability(
            tenant_id=self.tenant.pk,
            date_from=self.today,
            date_to=self.today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertEqual(result["sale_revenue"], Decimal("150.00"))
        self.assertEqual(result["covered_sale_revenue"], Decimal("100.00"))
        self.assertEqual(result["known_net_cogs"], Decimal("60.00"))
        self.assertEqual(result["known_gross_profit"], Decimal("40.00"))
        self.assertEqual(result["cost_coverage_percent"], Decimal("66.7"))
        self.assertEqual(result["incomplete_sale_lines"], 1)
        self.assertFalse(result["profitability_complete"])

    def test_selected_outlet_scopes_html_and_csv_profitability(self):
        self._paid_order(
            outlet=self.outlet,
            item=self.known_item,
            price="100.00",
            cost="60.00",
            trusted=True,
            key="profit-primary",
        )
        self._paid_order(
            outlet=self.other_outlet,
            item=self.known_item,
            price="900.00",
            cost="10.00",
            trusted=True,
            key="profit-other",
        )

        client = Client()
        self.assertTrue(
            client.login(username=self.user.email, password="Password9!")
        )
        session = client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

        response = client.get(
            reverse("staff-sales"),
            {
                "date_from": self.today.isoformat(),
                "date_to": self.today.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        profit = response.context["summary"]["merchandise_profitability"]
        self.assertEqual(profit["sale_revenue"], Decimal("100.00"))
        self.assertEqual(profit["known_net_cogs"], Decimal("60.00"))
        self.assertContains(response, "Historical merchandise profitability")
        self.assertNotContains(response, "900.00")

        csv_body = format_sales_summary_csv(
            self.tenant.pk,
            self.today,
            self.today,
            self.outlet.pk,
            allowed_outlet_ids=[self.outlet.pk, self.other_outlet.pk],
        )
        self.assertIn("merchandise_profitability_metric", csv_body)
        self.assertIn("net_merchandise_revenue,100.00,UGX", csv_body)
        self.assertIn("known_net_cogs,60.00,UGX", csv_body)
        self.assertNotIn("900.00", csv_body)
