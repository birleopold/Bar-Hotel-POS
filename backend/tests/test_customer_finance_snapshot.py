from decimal import Decimal

from django.test import TestCase
from django.template.loader import render_to_string

from apps.customers.models import Customer
from apps.lodging.models import Folio, FolioLine, FolioPayment
from apps.pos.models import Order
from apps.staff.services.customer_finance import customer_financial_snapshot
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class CustomerFinanceSnapshotTests(TestCase):
    def test_scoped_currency_totals_and_no_room_charge_double_count(self):
        tenant = Tenant.objects.create(name="Guest Ledger", slug="guest-ledger")
        site = Site.objects.create(tenant=tenant, name="Main")
        remote = Site.objects.create(tenant=tenant, name="Remote")
        outlet = Outlet.objects.create(site=site, name="Retail", outlet_type=OutletType.RETAIL)
        remote_outlet = Outlet.objects.create(site=remote, name="Remote retail", outlet_type=OutletType.RETAIL)
        guest = Customer.objects.create(tenant=tenant, name="Guest")
        Order.objects.create(tenant=tenant, outlet=outlet, customer=guest,
                             currency="UGX", total=Decimal("25000"), is_paid=True)
        Order.objects.create(tenant=tenant, outlet=remote_outlet, customer=guest,
                             currency="UGX", total=Decimal("80000"), is_paid=True)
        folio = Folio.objects.create(tenant=tenant, site=site, customer=guest,
                                    guest_name="Guest", currency="UGX")
        Order.objects.create(tenant=tenant, outlet=outlet, customer=guest, folio=folio,
                             currency="UGX", total=Decimal("12000"), is_paid=True)
        FolioLine.objects.create(tenant=tenant, folio=folio, description="Room / POS charge",
                                 amount=Decimal("12000"))
        FolioPayment.objects.create(tenant=tenant, folio=folio, amount=Decimal("5000"),
                                    method="cash", idempotency_key="test-guest-ledger")
        report = customer_financial_snapshot(
            tenant=tenant, customer=guest, site_ids=[site.pk], outlet_ids=[outlet.pk],
        )
        assert report["UGX"] == {
            "direct_pos_sales": Decimal("25000"),
            "folio_charges": Decimal("12000"),
            "folio_payments": Decimal("5000"),
            "outstanding": Decimal("7000"),
        }
        assert len(report) == 1

    def test_customer_financial_table_renders_currency_without_converting(self):
        html = render_to_string("staff/customers/detail.html", {
            "customer": {"name": "Guest", "email": "", "phone": ""},
            "financial_snapshot": {
                "UGX": {"direct_pos_sales": Decimal("10000"), "folio_charges": Decimal("5000"),
                        "folio_payments": Decimal("2000"), "outstanding": Decimal("3000")}
            },
            "can_merge": False,
        })
        self.assertIn("Financial summary by currency", html)
        self.assertIn("UGX", html)
        self.assertIn("10,000", html.replace(",", ","))
