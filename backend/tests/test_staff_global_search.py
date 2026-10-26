"""Security regression coverage for shared search and command palette.

The public search view and palette both use this same query service, preventing
independent feature-specific search bypasses.
"""
from pathlib import Path

from django.test import TestCase

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, MenuItemOutlet
from apps.customers.models import Customer
from apps.lodging.models import Reservation, ReservationStatus
from apps.pos.models import Order
from apps.purchasing.models import PurchaseOrder, Supplier
from apps.staff.services.search import staff_global_search
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class ScopedStaffSearchTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Search Tenant", slug="search-tenant-fixture")
        self.first_site = Site.objects.create(tenant=self.tenant, name="Site A")
        self.second_site = Site.objects.create(tenant=self.tenant, name="Site B")
        self.first = Outlet.objects.create(
            site=self.first_site, name="Store A", outlet_type=OutletType.RETAIL,
        )
        self.second = Outlet.objects.create(
            site=self.second_site, name="Store B", outlet_type=OutletType.RETAIL,
        )
        self.user = User.objects.create_user(email="search.manager@example.org")
        self.member = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.SITE_MANAGER,
        )
        self.member.sites.add(self.first_site)

    def search(self, query, membership=None, user=None, tenant=None):
        return staff_global_search(
            tenant=tenant or self.tenant, membership=membership or self.member,
            user=user or self.user, query=query,
        )

    @staticmethod
    def labels(groups):
        return [row["title"] for group in groups for row in group["items"]]

    def test_search_respects_outlet_and_site_scope(self):
        Order.objects.create(tenant=self.tenant, outlet=self.first, bill_reference="BILL-A-001")
        Order.objects.create(tenant=self.tenant, outlet=self.second, bill_reference="BILL-A-002")
        found = self.labels(self.search("BILL-A"))
        self.assertIn("BILL-A-001", found)
        self.assertNotIn("BILL-A-002", found)

    def test_guest_reservations_cannot_cross_property_boundary(self):
        from datetime import date
        Reservation.objects.create(
            tenant=self.tenant, site=self.first_site, guest_name="Search Jane A",
            check_in=date(2030, 1, 1), check_out=date(2030, 1, 2),
            status=ReservationStatus.CONFIRMED,
        )
        Reservation.objects.create(
            tenant=self.tenant, site=self.second_site, guest_name="Search Jane B",
            check_in=date(2030, 1, 1), check_out=date(2030, 1, 2),
            status=ReservationStatus.CONFIRMED,
        )
        found = self.labels(self.search("Search Jane"))
        self.assertIn("Search Jane A", found)
        self.assertNotIn("Search Jane B", found)

    def test_catalog_restrictions_do_not_leak_other_outlet_item(self):
        category = MenuCategory.objects.create(tenant=self.tenant, name="Stock")
        item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Secret carton",
            sku="SECRET-ONLY-B", unit_price="1000",
        )
        MenuItemOutlet.objects.create(menu_item=item, outlet=self.second)
        self.assertNotIn("Secret carton", self.labels(self.search("SECRET-ONLY-B")))

    def test_other_tenant_and_single_character_query_return_nothing(self):
        another = Tenant.objects.create(name="Other Tenant", slug="another-search-tenant")
        self.assertEqual(self.search("B", tenant=another), [])
        self.assertEqual(self.search("X"), [])

    def test_customer_scope_follows_shared_customer_policy(self):
        customer = Customer.objects.create(tenant=self.tenant, name="Guest Alma", email="alma@example.org")
        Order.objects.create(
            tenant=self.tenant, outlet=self.second, customer=customer,
            bill_reference="INVISIBLE-ORDER",
        )
        self.assertNotIn("Guest Alma", self.labels(self.search("Guest Alma")))

    def test_suppliers_and_purchase_orders_are_visible_to_manager(self):
        supplier = Supplier.objects.create(tenant=self.tenant, name="Search Distribution")
        PurchaseOrder.objects.create(
            tenant=self.tenant, outlet=self.first, supplier=supplier,
            reference="SUP-001",
        )
        groups = self.search("SUP-001")
        self.assertIn("SUP-001", self.labels(groups))

    def test_command_palette_has_live_trigger_and_safe_request_contract(self):
        root = Path(__file__).resolve().parents[1] / "apps" / "staff"
        nav = (root / "templates/staff/includes/nav.html").read_text(encoding="utf-8")
        palette = (root / "templates/staff/search/palette.html").read_text(encoding="utf-8")
        script = (root / "static/staff/staff-command.js").read_text(encoding="utf-8")

        self.assertIn("data-staff-command-open", nav)
        self.assertIn('data-search-url="{% url \'staff-search\' %}"', nav)
        self.assertIn("staff-command.js", palette)
        self.assertIn('trigger.getAttribute("data-search-url")', script)
        self.assertIn('credentials: "same-origin"', script)
        self.assertIn('cache: "no-store"', script)
        self.assertIn("response.redirected", script)
        self.assertIn('response.headers.get("Content-Type")', script)
        self.assertIn('type.includes("application/json")', script)

    def test_command_palette_cancels_stale_search_and_rejects_untrusted_links(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "apps" / "staff" / "static" / "staff" / "staff-command.js"
        ).read_text(encoding="utf-8")

        self.assertIn("if (controller) controller.abort();", script)
        self.assertIn("var thisGeneration = generation;", script)
        self.assertIn("if (thisGeneration !== generation || !dialog.open) return;", script)
        self.assertIn('error.name === "AbortError"', script)
        self.assertIn('!record.url.startsWith("/staff/")', script)
        self.assertIn('record.url.startsWith("//")', script)
        self.assertIn("title.textContent", script)
        self.assertNotIn("innerHTML", script)

    def test_results_are_bounded(self):
        for ix in range(11):
            Order.objects.create(
                tenant=self.tenant, outlet=self.first, bill_reference=f"FAST-{ix:03d}",
            )
        group = next(g for g in self.search("FAST-") if g["name"] == "Orders")
        self.assertLessEqual(len(group["items"]), 5)
