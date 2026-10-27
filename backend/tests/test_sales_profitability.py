from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

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

        api = APIClient()
        self.assertTrue(
            api.login(username=self.user.email, password="Password9!")
        )
        api_response = api.get(
            "/api/v1/reports/sales-summary/",
            {
                "date_from": self.today.isoformat(),
                "date_to": self.today.isoformat(),
                "outlet": str(self.outlet.pk),
            },
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(api_response.status_code, 200, api_response.content)
        api_profit = api_response.json()["merchandise_profitability"]
        self.assertEqual(api_profit["sale_revenue"], "100.00")
        self.assertEqual(api_profit["covered_net_revenue"], "100.00")
        self.assertEqual(api_profit["uncovered_net_revenue"], "0.00")
        self.assertEqual(api_profit["known_net_cogs"], "60.00")
        self.assertEqual(len(api_profit["categories"]), 1)
        self.assertEqual(
            api_profit["categories"][0]["category_name"],
            self.known_item.category.name,
        )
        self.assertNotIn("900.00", str(api_profit))

    def test_installment_sale_is_recognized_once_on_final_payment_date(self):
        previous = self.today - timedelta(days=1)
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            status=OrderStatus.CLOSED,
            subtotal=Decimal("100.00"),
            tax_total=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("100.00"),
            is_paid=True,
            created_by=self.user,
        )
        OrderLine.objects.create(
            order=order,
            menu_item=self.known_item,
            label=self.known_item.name,
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
            cost_unit_snapshot=Decimal("60.00"),
            cost_basis_complete_snapshot=True,
        )
        first = Payment.objects.create(
            tenant=self.tenant,
            order=order,
            amount=Decimal("40.00"),
            method="cash",
            idempotency_key="profit-partial-first",
            recorded_by=self.user,
        )
        final = Payment.objects.create(
            tenant=self.tenant,
            order=order,
            amount=Decimal("60.00"),
            method="cash",
            idempotency_key="profit-partial-final",
            recorded_by=self.user,
        )
        Payment.objects.filter(pk=first.pk).update(
            created_at=timezone.make_aware(datetime.combine(previous, time(12, 0)))
        )
        Payment.objects.filter(pk=final.pk).update(
            created_at=timezone.make_aware(datetime.combine(self.today, time(12, 0)))
        )

        previous_report = build_merchandise_profitability(
            tenant_id=self.tenant.pk,
            date_from=previous,
            date_to=previous,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        current_report = build_merchandise_profitability(
            tenant_id=self.tenant.pk,
            date_from=self.today,
            date_to=self.today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertEqual(previous_report["sale_revenue"], Decimal("0.00"))
        self.assertEqual(previous_report["known_net_cogs"], Decimal("0.00"))
        self.assertEqual(current_report["sale_revenue"], Decimal("100.00"))
        self.assertEqual(current_report["known_net_cogs"], Decimal("60.00"))
        self.assertEqual(current_report["known_gross_profit"], Decimal("40.00"))

    def test_outlet_profitability_coverage_and_unknown_cost_exposure(self):
        self._paid_order(
            outlet=self.outlet,
            item=self.known_item,
            price="100.00",
            cost="60.00",
            trusted=True,
            key="profit-outlet-known",
        )
        self._paid_order(
            outlet=self.other_outlet,
            item=self.unknown_item,
            price="250.00",
            cost=None,
            trusted=False,
            key="profit-outlet-unknown",
        )

        result = build_merchandise_profitability(
            tenant_id=self.tenant.pk,
            date_from=self.today,
            date_to=self.today,
            allowed_outlet_ids=[self.outlet.pk, self.other_outlet.pk],
            currency="UGX",
        )
        self.assertEqual(result["sale_revenue"], Decimal("350.00"))
        self.assertEqual(result["covered_sale_revenue"], Decimal("100.00"))
        self.assertEqual(result["uncovered_net_revenue"], Decimal("250.00"))

        rows = {row["outlet_id"]: row for row in result["outlets"]}
        known = rows[str(self.outlet.pk)]
        unknown = rows[str(self.other_outlet.pk)]
        self.assertEqual(known["net_revenue"], Decimal("100.00"))
        self.assertEqual(known["known_net_cogs"], Decimal("60.00"))
        self.assertEqual(known["known_gross_profit"], Decimal("40.00"))
        self.assertEqual(known["cost_coverage_percent"], Decimal("100.0"))
        self.assertTrue(known["profitability_complete"])

        self.assertEqual(unknown["net_revenue"], Decimal("250.00"))
        self.assertEqual(unknown["covered_net_revenue"], Decimal("0.00"))
        self.assertEqual(unknown["uncovered_net_revenue"], Decimal("250.00"))
        self.assertEqual(unknown["known_net_cogs"], Decimal("0.00"))
        self.assertEqual(unknown["cost_coverage_percent"], Decimal("0.0"))
        self.assertFalse(unknown["profitability_complete"])

        self.assertEqual(len(result["unknown_cost_exposure"]), 1)
        exposure = result["unknown_cost_exposure"][0]
        self.assertEqual(exposure["item_name"], self.unknown_item.name)
        self.assertEqual(exposure["sku"], self.unknown_item.sku)
        self.assertEqual(
            exposure["uncovered_net_revenue"], Decimal("250.00")
        )
        self.assertEqual(exposure["incomplete_lines"], 1)

        csv_body = format_sales_summary_csv(
            self.tenant.pk,
            self.today,
            self.today,
            allowed_outlet_ids=[self.outlet.pk, self.other_outlet.pk],
        )
        self.assertIn("merchandise_outlet", csv_body)
        self.assertIn(self.outlet.name, csv_body)
        self.assertIn(self.other_outlet.name, csv_body)
        self.assertIn("unknown_cost_product", csv_body)
        self.assertIn(self.unknown_item.name, csv_body)
        self.assertIn("250.00", csv_body)

