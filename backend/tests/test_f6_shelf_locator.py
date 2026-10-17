"""F6: searchable shelf locator, permissions, audit and stock conservation."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import AuditEvent
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance, StockShelfLocation
from apps.inventory.services_shelves import set_stock_shelf_location
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class ShelfLocatorTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="F6 Shelf Business", slug="f6-shelf-business")
        TenantSettings.objects.create(tenant=self.tenant, business_lines=["supermarket"], default_currency="UGX")
        site = Site.objects.create(tenant=self.tenant, name="Main supermarket")
        self.outlet = Outlet.objects.create(site=site, name="Ground floor", outlet_type=OutletType.SUPERMARKET)
        self.other_outlet = Outlet.objects.create(site=site, name="Backroom", outlet_type=OutletType.SUPERMARKET)
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Groceries")
        self.item = MenuItem.objects.create(
            tenant=self.tenant, category=cat, name="Rice 1kg",
            sku="RICE-1", barcode="8901012", unit_price=Decimal("6000"),
            track_inventory=True,
        )
        self.balance = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.item, quantity=Decimal("23"),
        )
        self.user = User.objects.create_user(email="f6-shelf-manager@example.test", password="Password123!")
        self.membership = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OUTLET_MANAGER,
        )
        self.membership.sites.add(site)
        self.membership.outlets.add(self.outlet)
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def save_shelf(self, **kwargs):
        return set_stock_shelf_location(
            tenant_id=self.tenant.pk, outlet_id=self.outlet.pk,
            menu_item_id=self.item.pk, aisle="A3", shelf="Middle",
            bin_code="B12", note="Next to sugar",
            membership=self.membership, user=self.user, **kwargs,
        )

    def test_shelf_assignment_and_identical_replay_do_not_move_inventory(self):
        first, replay = self.save_shelf()
        self.assertFalse(replay)
        self.assertEqual(first.aisle, "A3")
        again, repeated = self.save_shelf()
        self.assertTrue(repeated)
        self.assertEqual(again.pk, first.pk)
        self.assertEqual(StockShelfLocation.objects.count(), 1)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, Decimal("23"))
        self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant, action="stock.shelf_location_saved").count(), 1)

    def test_outlet_scope_and_readonly_role_are_enforced(self):
        with self.assertRaises(ValidationError):
            set_stock_shelf_location(
                tenant_id=self.tenant.pk, outlet_id=self.other_outlet.pk, menu_item_id=self.item.pk,
                aisle="Z1", membership=self.membership, user=self.user,
            )
        self.membership.role = MembershipRole.ACCOUNTANT
        self.membership.save(update_fields=["role"])
        with self.assertRaises(ValidationError):
            self.save_shelf()
        self.assertFalse(StockShelfLocation.objects.exists())

    def test_cross_tenant_item_cannot_be_assigned(self):
        other = Tenant.objects.create(name="Elsewhere", slug="elsewhere-f6-shelf")
        category = MenuCategory.objects.create(tenant=other, name="Other")
        item = MenuItem.objects.create(
            tenant=other, category=category, name="Private item",
            unit_price=Decimal("90"), track_inventory=True,
        )
        with self.assertRaises(ValidationError):
            set_stock_shelf_location(
                tenant_id=self.tenant.pk, outlet_id=self.outlet.pk, menu_item_id=item.pk,
                aisle="A1", membership=self.membership, user=self.user,
            )
        self.assertFalse(StockShelfLocation.objects.exists())

    def test_staff_ui_finds_shelf_by_code_and_scopes_edit(self):
        page = self.client.get(reverse("staff-inventory-shelves"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Rice 1kg")
        self.assertContains(page, "Edit location")
        response = self.client.post(reverse("staff-inventory-shelves"), {
            "outlet_id": str(self.outlet.pk), "menu_item_id": str(self.item.pk),
            "aisle": "A3", "shelf": "Middle", "bin_code": "B12", "note": "Left of sugar",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockShelfLocation.objects.count(), 1)
        by_location = self.client.get(reverse("staff-inventory-shelves"), {"q": "B12"})
        self.assertEqual(by_location.status_code, 200)
        self.assertContains(by_location, "Rice 1kg")
        self.assertContains(by_location, "A3")
        blocked = self.client.post(reverse("staff-inventory-shelves"), {
            "outlet_id": str(self.other_outlet.pk), "menu_item_id": str(self.item.pk),
            "aisle": "Not allowed",
        })
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(StockShelfLocation.objects.count(), 1)

    def test_staff_location_not_visible_when_outlet_is_unassigned(self):
        StockShelfLocation.objects.create(
            tenant=self.tenant, outlet=self.other_outlet, menu_item=self.item, aisle="SECRET",
        )
        page = self.client.get(reverse("staff-inventory-shelves"), {"q": "SECRET"})
        self.assertEqual(page.status_code, 200)
        # Search text remains in the search field; only result rows are secret.
        self.assertContains(page, "No products found")
        self.assertEqual(list(page.context["balances"]), [])


    def test_api_shelf_lookup_and_assignment_are_outlet_scoped(self):
        from rest_framework.test import APIClient

        api = APIClient()
        assert api.login(username=self.user.email, password="Password123!")
        url = reverse("stock-shelf-location-list")
        headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}
        posted = api.post(url, {
            "outlet_id": str(self.outlet.pk), "menu_item_id": str(self.item.pk),
            "aisle": "B1", "shelf": "Lower", "bin_code": "BX3",
        }, format="json", **headers)
        self.assertEqual(posted.status_code, 201, posted.content)
        self.assertEqual(posted.data["aisle"], "B1")
        matches = api.get(url, {"q": "BX3"}, **headers)
        self.assertEqual(matches.status_code, 200)
        self.assertEqual(len(matches.data), 1)
        denied = api.post(url, {
            "outlet_id": str(self.other_outlet.pk), "menu_item_id": str(self.item.pk),
            "aisle": "PRIVATE",
        }, format="json", **headers)
        self.assertEqual(denied.status_code, 400, denied.content)
        self.assertEqual(StockShelfLocation.objects.count(), 1)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, Decimal("23"))
