"""Retail shelf-label printing uses the existing tenant/outlet catalog."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, MenuItemOutlet, UnitOfMeasure
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class RetailShelfLabelTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Label Grocery", slug="label-grocery")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Main supermarket",
            outlet_type=OutletType.SUPERMARKET,
        )
        category = MenuCategory.objects.create(tenant=self.tenant, name="Soap")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=category,
            name="Geisha Soap",
            sku="GEISHA-175",
            barcode="6001234567890",
            unit_of_measure=UnitOfMeasure.EACH,
            unit_price=Decimal("5000.00"),
            is_active=True,
        )
        MenuItemOutlet.objects.create(
            menu_item=self.item,
            outlet=self.outlet,
            price_override=Decimal("5500.00"),
        )

        foreign = Tenant.objects.create(name="Foreign Shop", slug="foreign-label-shop")
        TenantSettings.objects.create(tenant=foreign, business_lines=["supermarket"])
        foreign_category = MenuCategory.objects.create(tenant=foreign, name="Private")
        MenuItem.objects.create(
            tenant=foreign,
            category=foreign_category,
            name="Foreign Secret Product",
            sku="FOREIGN-1",
            barcode="7000000000001",
            unit_price=Decimal("1.00"),
            is_active=True,
        )

        self.user = User.objects.create_user(
            email="label-owner@example.test",
            password="StrongPassword!2026",
        )
        membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=MembershipRole.OWNER,
        )
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet)
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        self.url = reverse("staff-inventory-shelf-labels")

    def test_label_screen_uses_outlet_price_and_keeps_foreign_items_out(self):
        response = self.client.get(self.url, {"outlet": str(self.outlet.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shelf &amp; price labels", html=False)
        self.assertContains(response, "Geisha Soap")
        self.assertContains(response, "UGX 5500.00")
        self.assertContains(response, "6001234567890")
        self.assertNotContains(response, "Foreign Secret Product")

    def test_selected_product_generates_private_pdf_with_real_barcode(self):
        response = self.client.post(self.url, {
            "outlet": str(self.outlet.pk),
            "item_ids": [str(self.item.pk)],
            f"copies_{self.item.pk}": "2",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("shelf-labels.pdf", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertGreater(len(response.content), 1000)

    def test_foreign_or_excessive_label_requests_fail_closed(self):
        foreign = MenuItem.objects.exclude(tenant=self.tenant).first()
        response = self.client.post(self.url, {
            "outlet": str(self.outlet.pk),
            "item_ids": [str(foreign.pk)],
            f"copies_{foreign.pk}": "1",
        })
        self.assertEqual(response.status_code, 302)

        response = self.client.post(self.url, {
            "outlet": str(self.outlet.pk),
            "item_ids": [str(self.item.pk)],
            f"copies_{self.item.pk}": "21",
        })
        self.assertEqual(response.status_code, 302)
