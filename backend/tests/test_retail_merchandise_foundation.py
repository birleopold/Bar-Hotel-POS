from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.catalog.models import MenuCategory, MenuItem, ProductFamily, ProductPackage
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Tenant, TenantSettings


User = get_user_model()


class RetailMerchandiseFoundationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Retail merchandise", slug="retail-merchandise")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "inventory", "purchasing"],
        )
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="General")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Mineral Water",
            sku="WATER-500",
            barcode="100000000001",
            unit_price=Decimal("1000"),
            track_inventory=True,
        )
        self.owner = User.objects.create_user(
            email="retail-merchandise@test.local", password="Password9!",
        )
        Membership.objects.create(
            tenant=self.tenant, user=self.owner, role=MembershipRole.OWNER,
        )
        self.client.force_login(self.owner)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session.save()

    def test_simple_products_remain_valid_without_family_or_packages(self):
        self.item.refresh_from_db()
        self.assertIsNone(self.item.product_family)
        self.assertEqual(self.item.packages.count(), 0)
        response = self.client.get(reverse("console-org-menu-item-edit", args=[self.item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Packages &amp; barcodes")

    def test_owner_can_create_family_and_assign_product(self):
        response = self.client.post(
            reverse("console-org-product-family-create"),
            {
                "category": str(self.category.pk),
                "name": "Mineral Water",
                "description": "Bottle sizes",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        family = ProductFamily.objects.get(tenant=self.tenant, name="Mineral Water")
        self.assertEqual(family.category, self.category)

        response = self.client.post(
            reverse("console-org-menu-item-edit", args=[self.item.pk]),
            {
                "category": str(self.category.pk),
                "product_family": str(family.pk),
                "name": self.item.name,
                "description": "",
                "display_image_url": "",
                "sku": self.item.sku,
                "barcode": self.item.barcode,
                "unit_of_measure": "each",
                "units_per_carton": "1",
                "track_inventory": "on",
                "reorder_level": "",
                "unit_price": "1000",
                "tax_rate_percent": "",
                "is_active": "on",
                "kds_station": "",
                "consume_recipe_on_sale": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.product_family, family)

    def test_owner_can_manage_package_definition_from_product_ui(self):
        response = self.client.post(
            reverse("console-org-menu-item-package-create", args=[self.item.pk]),
            {
                "name": "Case of 24",
                "units_per_package": "24",
                "barcode": "240000000001",
                "sku_alias": "WATER-500-24",
                "sell_price": "22000",
                "is_sellable": "on",
                "is_purchasable": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        package = ProductPackage.objects.get(menu_item=self.item)
        self.assertEqual(package.tenant, self.tenant)
        self.assertEqual(package.units_per_package, Decimal("24"))
        self.assertEqual(package.sell_price, Decimal("22000"))

        listing = self.client.get(reverse("console-org-menu-item-packages", args=[self.item.pk]))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Case of 24")
        self.assertContains(listing, "240000000001")

    def test_package_barcode_cannot_duplicate_another_product(self):
        other = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Soap",
            barcode="SOAP-CODE",
            unit_price=Decimal("3500"),
        )
        response = self.client.post(
            reverse("console-org-menu-item-package-create", args=[self.item.pk]),
            {
                "name": "Shrink pack",
                "units_per_package": "6",
                "barcode": other.barcode,
                "sku_alias": "",
                "sell_price": "",
                "is_sellable": "on",
                "is_purchasable": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered to another product")
        self.assertFalse(ProductPackage.objects.filter(menu_item=self.item).exists())

    def test_base_product_code_cannot_reuse_package_code(self):
        ProductPackage.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            name="Case",
            units_per_package=Decimal("12"),
            barcode="PACKAGE-BARCODE",
            sku_alias="PACKAGE-SKU",
        )
        response = self.client.post(
            reverse("console-org-menu-item-edit", args=[self.item.pk]),
            {
                "category": str(self.category.pk),
                "product_family": "",
                "name": self.item.name,
                "description": "",
                "display_image_url": "",
                "sku": "PACKAGE-SKU",
                "barcode": "PACKAGE-BARCODE",
                "unit_of_measure": "each",
                "units_per_carton": "1",
                "track_inventory": "on",
                "reorder_level": "",
                "unit_price": "1000",
                "tax_rate_percent": "",
                "is_active": "on",
                "kds_station": "",
                "consume_recipe_on_sale": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already assigned to a product package")
        self.item.refresh_from_db()
        self.assertEqual(self.item.barcode, "100000000001")
        self.assertEqual(self.item.sku, "WATER-500")

    def test_other_tenant_product_is_not_available_through_package_routes(self):
        other_tenant = Tenant.objects.create(name="Other shop", slug="other-shop-merch")
        TenantSettings.objects.create(tenant=other_tenant, business_lines=["supermarket"])
        other_category = MenuCategory.objects.create(tenant=other_tenant, name="General")
        other_item = MenuItem.objects.create(
            tenant=other_tenant,
            category=other_category,
            name="Foreign item",
            unit_price=Decimal("1"),
        )
        response = self.client.get(reverse("console-org-menu-item-packages", args=[other_item.pk]))
        self.assertEqual(response.status_code, 404)
