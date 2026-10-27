from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    ProductPackage,
    RetailProductGroup,
    RetailProductGroupLine,
    SupermarketSkuProfile,
)
from apps.pos.models import Order
from apps.pos.services import add_retail_group_to_open_order
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings
from rest_framework.exceptions import ValidationError


class RetailProductGroupTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Retail groups", slug="retail-groups")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "inventory", "purchasing", "promotions", "workspace"],
            default_currency="UGX",
            hardware_barcode_scanner_enabled=True,
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main store")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Checkout", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="groups@test.local", password="Password9!")
        self.membership = Membership.objects.create(
            user=self.user, tenant=self.tenant, role=MembershipRole.OWNER,
        )
        self.membership.sites.add(self.site)
        self.membership.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="General")
        self.soap = MenuItem.objects.create(
            tenant=self.tenant, category=self.category, name="Soap",
            sku="SOAP-1", barcode="SOAP-BC", unit_price=Decimal("3000"),
            track_inventory=False,
        )
        self.lotion = MenuItem.objects.create(
            tenant=self.tenant, category=self.category, name="Lotion",
            sku="LOTION-1", barcode="LOTION-BC", unit_price=Decimal("5000"),
            track_inventory=False,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def _group(self):
        group = RetailProductGroup.objects.create(
            tenant=self.tenant, name="Gift set", code="GIFTSET",
        )
        RetailProductGroupLine.objects.create(
            tenant=self.tenant, group=group, menu_item=self.soap, quantity=Decimal("2"), sort_order=1,
        )
        RetailProductGroupLine.objects.create(
            tenant=self.tenant, group=group, menu_item=self.lotion, quantity=Decimal("1"), sort_order=2,
        )
        return group

    def _order(self):
        return Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user, currency="UGX",
        )

    def test_owner_can_configure_group_and_component_ui(self):
        create = self.client.post(
            reverse("console-org-retail-group-create"),
            {
                "name": "School set",
                "code": "SCHOOLSET",
                "description": "Quick checkout set",
                "is_active": "on",
            },
        )
        self.assertEqual(create.status_code, 302)
        group = RetailProductGroup.objects.get(name="School set")
        line_create = self.client.post(
            reverse("console-org-retail-group-line-create", args=[group.pk]),
            {
                "menu_item": str(self.soap.pk),
                "quantity": "3",
                "sort_order": "1",
            },
        )
        self.assertEqual(line_create.status_code, 302)
        listing = self.client.get(reverse("console-org-retail-group-lines", args=[group.pk]))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Soap")
        self.assertContains(listing, "3.000")

    def test_checkout_exposes_group_shortcuts_on_lossless_async_queue(self):
        group = self._group()
        order = self._order()
        response = self.client.get(reverse("staff-order-detail", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quick groups")
        self.assertContains(response, group.name)
        self.assertContains(response, group.code)
        self.assertContains(response, "data-retail-group-form")

    def test_async_group_add_expands_to_normal_component_lines(self):
        group = self._group()
        order = self._order()
        response = self.client.post(
            reverse("staff-order-detail", args=[order.pk]),
            {
                "action": "add_retail_group",
                "retail_group_id": str(group.pk),
                "quantity": "2",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        lines = {
            line.menu_item_id: line
            for line in order.lines.filter(is_voided=False).select_related("menu_item")
        }
        self.assertEqual(lines[self.soap.pk].quantity, Decimal("4"))
        self.assertEqual(lines[self.lotion.pk].quantity, Decimal("2"))
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("22000.00"))

    def test_repeated_group_taps_merge_component_lines_without_duplicates(self):
        group = self._group()
        order = self._order()
        url = reverse("staff-order-detail", args=[order.pk])
        payload = {
            "action": "add_retail_group",
            "retail_group_id": str(group.pk),
            "quantity": "1",
        }
        for _ in range(3):
            response = self.client.post(
                url,
                payload,
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["ok"])
        order.refresh_from_db()
        self.assertEqual(order.lines.filter(is_voided=False).count(), 2)
        self.assertEqual(order.lines.get(menu_item=self.soap).quantity, Decimal("6"))
        self.assertEqual(order.lines.get(menu_item=self.lotion).quantity, Decimal("3"))
        self.assertEqual(order.total, Decimal("33000.00"))

    def test_scanner_group_code_uses_same_atomic_expansion(self):
        group = self._group()
        order = self._order()
        response = self.client.post(
            reverse("staff-order-detail", args=[order.pk]),
            {
                "action": "scan_add_line",
                "code": group.code,
                "quantity": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(order.lines.filter(is_voided=False).count(), 2)
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("11000.00"))

    def test_invalid_component_rolls_back_entire_group_add(self):
        group = self._group()
        self.lotion.is_active = False
        self.lotion.save(update_fields=["is_active"])
        order = self._order()
        with self.assertRaises(ValidationError):
            add_retail_group_to_open_order(
                order=order,
                retail_group=group,
                quantity=Decimal("1"),
                user=self.user,
            )
        self.assertFalse(order.lines.exists())

    def test_empty_group_is_not_exposed_on_checkout(self):
        RetailProductGroup.objects.create(
            tenant=self.tenant, name="Empty", code="EMPTYSET",
        )
        order = self._order()
        response = self.client.get(reverse("staff-order-detail", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "EMPTYSET")

    def test_group_code_cannot_reuse_active_plu(self):
        SupermarketSkuProfile.objects.create(
            tenant=self.tenant,
            menu_item=self.soap,
            plu_code="4455",
            is_active=True,
        )
        response = self.client.post(
            reverse("console-org-retail-group-create"),
            {
                "name": "PLU collision",
                "code": "4455",
                "description": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already belongs to an active product PLU")
        self.assertFalse(RetailProductGroup.objects.filter(name="PLU collision").exists())

    def test_legacy_group_code_collision_defers_to_real_product_plu(self):
        SupermarketSkuProfile.objects.create(
            tenant=self.tenant,
            menu_item=self.soap,
            plu_code="5566",
            is_active=True,
        )
        legacy = RetailProductGroup.objects.create(
            tenant=self.tenant,
            name="Legacy collision",
            code="5566",
        )
        RetailProductGroupLine.objects.create(
            tenant=self.tenant,
            group=legacy,
            menu_item=self.lotion,
            quantity=Decimal("1"),
        )
        order = self._order()
        response = self.client.post(
            reverse("staff-order-detail", args=[order.pk]),
            {
                "action": "scan_add_line",
                "code": "5566",
                "quantity": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(order.lines.filter(menu_item=self.soap, is_voided=False).count(), 1)
        self.assertFalse(order.lines.filter(menu_item=self.lotion, is_voided=False).exists())

    def test_group_code_cannot_reuse_product_or_package_code(self):
        response = self.client.post(
            reverse("console-org-retail-group-create"),
            {
                "name": "Bad group",
                "code": self.soap.sku,
                "description": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already belongs to a product barcode or SKU")
        self.assertFalse(RetailProductGroup.objects.filter(name="Bad group").exists())

        group = RetailProductGroup.objects.create(
            tenant=self.tenant, name="Group code owner", code="OWNEDCODE",
        )
        package_response = self.client.post(
            reverse("console-org-menu-item-package-create", args=[self.soap.pk]),
            {
                "name": "Pack",
                "units_per_package": "2",
                "barcode": "OWNEDCODE",
                "sku_alias": "",
                "sell_price": "",
                "is_sellable": "on",
                "is_purchasable": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(package_response.status_code, 200)
        self.assertContains(package_response, "already used by a retail product group")
        self.assertFalse(ProductPackage.objects.filter(menu_item=self.soap).exists())
