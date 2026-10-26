"""Regression checks for the store-owner console, separate from hospitality administration."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.audit.models import AuditEvent
from apps.catalog.models import MenuCategory, MenuItem, MenuItemOutlet
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
        self.assertContains(response, "Set up your workspace")
        self.assertContains(response, "Required setup progress")
        self.assertContains(response, "Opening checks")
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

    def test_sales_area_pages_keep_tenant_brand_and_do_not_expose_hotel_labels(self):
        index = self.client.get(reverse("console-org-outlets", kwargs={"site_id": self.site.pk}))
        create = self.client.get(reverse("console-org-outlet-create", kwargs={"site_id": self.site.pk}))
        for response in (index, create):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, self.tenant.name)
            self.assertNotContains(response, "FIZO /")
            self.assertNotContains(response, "Hotel dashboard")
        self.assertContains(index, "Sales areas")
        self.assertContains(index, "Manage checkout and sales areas at")
        self.assertNotContains(index, "Manage service sections at")
        self.assertContains(index, "Add sales area")
        self.assertContains(create, "Save sales area")
        self.assertContains(create, "Create the checkout or sales area staff will use")
        self.assertNotContains(create, "Configure the service section your team will use.")

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

    def test_catalog_selling_price_changes_are_audited(self):
        response = self.client.post(
            reverse("console-org-menu-item-edit", kwargs={"item_id": self.product.pk}),
            {
                "category": str(self.category.pk),
                "name": self.product.name,
                "description": "",
                "sku": "",
                "barcode": "",
                "unit_of_measure": "each",
                "units_per_carton": "1",
                "track_inventory": "",
                "reorder_level": "",
                "unit_price": "5500.00",
                "tax_rate_percent": "",
                "is_active": "on",
                "kds_station": "",
                "consume_recipe_on_sale": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.unit_price, Decimal("5500.00"))
        base_event = AuditEvent.objects.get(
            tenant=self.tenant,
            action="catalog.unit_price_changed",
            entity_id=str(self.product.pk),
        )
        self.assertEqual(base_event.user_id, self.user.pk)
        self.assertEqual(base_event.payload["before"], "5000.00")
        self.assertEqual(base_event.payload["after"], "5500.00")
        self.assertTrue(base_event.payload["applies_to_all_outlets"])

        link = MenuItemOutlet.objects.create(
            menu_item=self.product,
            outlet=self.outlet,
            price_override=None,
        )
        response = self.client.post(
            reverse(
                "console-org-menu-item-outlet-edit",
                kwargs={"item_id": self.product.pk, "link_id": link.pk},
            ),
            {"price_override": "4800.00"},
        )
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual(link.price_override, Decimal("4800.00"))
        override_event = AuditEvent.objects.filter(
            tenant=self.tenant,
            action="catalog.outlet_price_override_changed",
            entity_id=str(link.pk),
        ).latest("created_at")
        self.assertEqual(override_event.user_id, self.user.pk)
        self.assertEqual(override_event.payload["outlet_id"], str(self.outlet.pk))
        self.assertEqual(override_event.payload["before"], "5500.00")
        self.assertEqual(override_event.payload["after"], "4800.00")

        response = self.client.post(
            reverse(
                "console-org-menu-item-outlet-delete",
                kwargs={"item_id": self.product.pk, "link_id": link.pk},
            ),
            {},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(MenuItemOutlet.objects.filter(pk=link.pk).exists())
        removal_event = AuditEvent.objects.filter(
            tenant=self.tenant,
            action="catalog.outlet_price_override_changed",
            entity_id=str(link.pk),
        ).latest("created_at")
        self.assertTrue(removal_event.payload["link_removed"])
        self.assertEqual(removal_event.payload["before"], "4800.00")
        self.assertEqual(removal_event.payload["after"], "5500.00")

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
