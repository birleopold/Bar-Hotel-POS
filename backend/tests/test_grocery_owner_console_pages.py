"""Regression checks for the store-owner console, separate from hospitality administration."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.catalog.models import MenuCategory, MenuItem
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings

User = get_user_model()


class GroceryOwnerConsolePagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Corner Grocers", slug="corner-grocers")
        TenantSettings.objects.create(
            tenant=cls.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "inventory", "purchasing", "workspace"],
        )
        cls.user = User.objects.create_user(
            email="grocery-owner-console@example.test",
            password="TestPass9!",
        )
        Membership.objects.create(user=cls.user, tenant=cls.tenant, role=MembershipRole.OWNER)
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main Store")
        cls.outlet = Outlet.objects.create(
            site=cls.site, name="Main shop", outlet_type=OutletType.SUPERMARKET,
        )
        cls.category = MenuCategory.objects.create(tenant=cls.tenant, name="Groceries")
        cls.product = MenuItem.objects.create(
            tenant=cls.tenant,
            category=cls.category,
            name="Rice 1kg",
            unit_price=Decimal("5000.00"),
        )

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session.save()

    def test_grocery_owner_gets_new_shell_on_main_console_routes(self):
        routes = (
            "console-org", "console-org-setup", "console-org-sites",
            "console-org-site-create", "console-org-menu-items",
            "console-org-menu-item-create", "console-org-menu-categories",
            "console-org-menu-category-create",
        )
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["grocery_console_shell"])
                self.assertContains(response, "grocery-console-body")
                self.assertContains(response, 'aria-label="Store management"')

    def test_step_by_step_setup_preserves_actual_progress_data_and_actions(self):
        response = self.client.get(reverse("console-org-setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete these steps")
        self.assertContains(response, "Required setup progress")
        self.assertContains(response, "Before your first sale")
        self.assertContains(response, reverse("console-org-setup-step-state"))
        self.assertContains(response, reverse("console-org-sites"))

    def test_products_categories_and_sales_areas_use_retail_language(self):
        response = self.client.get(reverse("console-org-menu-items"))
        self.assertContains(response, "Your products")
        self.assertContains(response, "Rice 1kg")
        self.assertContains(response, "Branch pricing")
        self.assertNotContains(response, "Modifier groups")
        self.assertNotContains(response, ">Recipe</a>")
        response = self.client.get(reverse("console-org-menu-categories"))
        self.assertContains(response, "Product categories")
        response = self.client.get(
            reverse("console-org-outlets", kwargs={"site_id": self.site.pk})
        )
        self.assertContains(response, "Sales areas")
        self.assertContains(response, "Main shop")
        response = self.client.get(
            reverse("console-org-outlet-create", kwargs={"site_id": self.site.pk})
        )
        self.assertContains(response, "Save sales area")

    def test_product_editor_keeps_advanced_inputs_available(self):
        response = self.client.get(
            reverse("console-org-menu-item-edit", kwargs={"item_id": self.product.pk})
        )
        self.assertContains(response, "Advanced product options")
        self.assertContains(response, 'name="modifier_groups"')
        self.assertContains(response, 'name="outlets"')
        self.assertNotContains(response, "Recipe / bill of materials")
        response = self.client.get(
            reverse("console-org-menu-item-outlets", kwargs={"item_id": self.product.pk})
        )
        self.assertContains(response, "Prices by sales area")
        self.assertContains(response, "One price for all sales areas")

    def test_store_branch_form_still_validates_submissions(self):
        response = self.client.post(
            reverse("console-org-site-create"),
            {
                "name": "",
                "city": "Kampala",
                "country_code": "UG",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")

    def test_retail_only_combined_business_profile_keeps_store_shell(self):
        settings = self.tenant.settings
        settings.business_lines = ["retail", "supermarket"]
        settings.save(update_fields=["business_lines", "updated_at"])
        response = self.client.get(reverse("console-org"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["grocery_console_shell"])
        self.assertContains(response, "Your store settings")

    def test_hospitality_profile_keeps_existing_administration(self):
        settings = self.tenant.settings
        settings.business_lines = ["bar"]
        settings.save(update_fields=["business_lines", "updated_at"])
        response = self.client.get(reverse("console-org"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["grocery_console_shell"])
        self.assertContains(response, "Organization overview")
        self.assertContains(response, 'aria-label="Administration navigation"')
        self.assertNotContains(response, 'aria-label="Store management"')
        self.assertNotContains(response, 'class="grocery-setup"')
