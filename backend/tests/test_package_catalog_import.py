from decimal import Decimal
from io import StringIO
import csv

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import AuditEvent
from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    ProductPackage,
    SupermarketSkuProfile,
)
from apps.console.catalog_import import (
    CatalogImportProblem,
    import_product_packages,
    parse_package_csv,
)
from apps.inventory.models import StockBalance, StockMovement
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


def package_file(text, name="packages.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class PackageCatalogImportTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Package CSV", slug="package-csv")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "inventory", "purchasing", "workspace"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Shop", outlet_type=OutletType.SUPERMARKET,
        )
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Drinks")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Mineral water 500ml",
            sku="WATER-500",
            barcode="600100000001",
            unit_price=Decimal("1000"),
            track_inventory=True,
        )
        self.user = User.objects.create_user(
            email="package-csv@test.local", password="Password9!",
        )
        Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OWNER,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session.save()

    def _csv(self, row):
        return (
            "product_sku,product_name,package_name,units_per_package,barcode,"
            "sku_alias,sell_price,is_sellable,is_purchasable,is_active\n"
            + row
            + "\n"
        )

    def test_preview_and_import_create_packages_without_stock(self):
        text = self._csv(
            "WATER-500,Mineral water 500ml,Case of 24,24,600100000024,"
            "WATER-500-24,24000,yes,yes,yes"
        )
        url = reverse("console-org-catalog-import")
        preview = self.client.post(
            url,
            {"action": "preview_packages", "package_file": package_file(text)},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "1 package rows passed validation")
        self.assertContains(preview, "Case of 24")
        self.assertFalse(ProductPackage.objects.filter(tenant=self.tenant).exists())

        imported = self.client.post(
            url,
            {"action": "import_packages", "package_file": package_file(text)},
        )
        self.assertEqual(imported.status_code, 302)
        package = ProductPackage.objects.get(tenant=self.tenant, menu_item=self.item)
        self.assertEqual(package.name, "Case of 24")
        self.assertEqual(package.units_per_package, Decimal("24"))
        self.assertEqual(package.barcode, "600100000024")
        self.assertEqual(package.sku_alias, "WATER-500-24")
        self.assertEqual(package.sell_price, Decimal("24000"))
        self.assertFalse(StockBalance.objects.filter(menu_item=self.item).exists())
        self.assertFalse(StockMovement.objects.filter(menu_item=self.item).exists())
        event = AuditEvent.objects.get(
            tenant=self.tenant, action="catalog.csv_packages_imported",
        )
        self.assertEqual(event.payload["count"], 1)

    def test_package_export_is_tenant_scoped_and_spreadsheet_safe(self):
        ProductPackage.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            name="=Case 24",
            units_per_package=Decimal("24"),
            barcode="600100000024",
            sku_alias="WATER24",
        )
        other = Tenant.objects.create(name="Other package CSV", slug="other-package-csv")
        TenantSettings.objects.create(tenant=other, business_lines=["supermarket"])
        other_category = MenuCategory.objects.create(tenant=other, name="Other")
        other_item = MenuItem.objects.create(
            tenant=other,
            category=other_category,
            name="Other item",
            sku="OTHER-1",
            unit_price=Decimal("1"),
        )
        ProductPackage.objects.create(
            tenant=other,
            menu_item=other_item,
            name="Other pack",
            units_per_package=Decimal("2"),
        )

        response = self.client.get(
            reverse("console-org-catalog-import"), {"packages_export": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        rows = list(csv.DictReader(StringIO(response.content.decode("utf-8"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product_sku"], "WATER-500")
        self.assertEqual(rows[0]["package_name"], "'=Case 24")
        self.assertNotIn("OTHER-1", response.content.decode("utf-8"))

    def test_package_import_rejects_scanner_collisions_atomically(self):
        text = (
            "product_sku,package_name,units_per_package,barcode,sku_alias\n"
            "WATER-500,Good case,6,NEW-PACK-6,WATER-6\n"
            "WATER-500,Bad case,12,600100000001,WATER-12\n"
        )
        with self.assertRaises(CatalogImportProblem) as raised:
            parse_package_csv(tenant=self.tenant, uploaded=package_file(text))
        self.assertIn("scanner identity", str(raised.exception).lower())
        self.assertFalse(ProductPackage.objects.filter(tenant=self.tenant).exists())

    def test_package_import_rejects_active_plu_and_duplicate_codes(self):
        SupermarketSkuProfile.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            plu_code="4455",
            is_active=True,
        )
        with self.assertRaises(CatalogImportProblem):
            parse_package_csv(
                tenant=self.tenant,
                uploaded=package_file(
                    "product_sku,package_name,units_per_package,barcode\n"
                    "WATER-500,PLU pack,2,4455\n"
                ),
            )
        with self.assertRaises(CatalogImportProblem) as raised:
            parse_package_csv(
                tenant=self.tenant,
                uploaded=package_file(
                    "product_sku,package_name,units_per_package,barcode,sku_alias\n"
                    "WATER-500,Same code,2,SAME-CODE,same-code\n"
                ),
            )
        self.assertIn("must be different", str(raised.exception))

    def test_package_import_requires_unique_existing_product_sku(self):
        MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Duplicate SKU product",
            sku="water-500",
            unit_price=Decimal("2000"),
        )
        with self.assertRaises(CatalogImportProblem) as raised:
            parse_package_csv(
                tenant=self.tenant,
                uploaded=package_file(
                    "product_sku,package_name,units_per_package\n"
                    "WATER-500,Case,24\n"
                ),
            )
        self.assertIn("multiple products", str(raised.exception).lower())

    def test_package_sell_price_must_map_exactly_to_current_line_price_precision(self):
        with self.assertRaises(CatalogImportProblem) as raised:
            parse_package_csv(
                tenant=self.tenant,
                uploaded=package_file(
                    "product_sku,package_name,units_per_package,sell_price\n"
                    "WATER-500,Three pack,3,1000.00\n"
                ),
            )
        self.assertIn("divide exactly", str(raised.exception))

    def test_import_rechecks_identity_after_preview_before_writing(self):
        rows = parse_package_csv(
            tenant=self.tenant,
            uploaded=package_file(
                "product_sku,package_name,units_per_package,barcode\n"
                "WATER-500,Case,24,CASE-24\n"
            ),
        )
        ProductPackage.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            name="Other",
            units_per_package=Decimal("2"),
            barcode="CASE-24",
        )
        with self.assertRaises(CatalogImportProblem):
            import_product_packages(tenant=self.tenant, rows=rows)
        self.assertEqual(ProductPackage.objects.filter(tenant=self.tenant).count(), 1)

    def test_package_workflow_is_hidden_from_hospitality_only_tenant(self):
        self.tenant.settings.business_lines = ["bar"]
        self.tenant.settings.save(update_fields=["business_lines"])
        url = reverse("console-org-catalog-import")
        response = self.client.get(url, {"packages_export": "1"})
        self.assertEqual(response.status_code, 404)
        post = self.client.post(
            url,
            {
                "action": "preview_packages",
                "package_file": package_file(
                    "product_sku,package_name,units_per_package\n"
                    "WATER-500,Case,24\n"
                ),
            },
        )
        self.assertEqual(post.status_code, 404)

    def test_package_editor_rejects_plu_and_same_barcode_alias(self):
        SupermarketSkuProfile.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            plu_code="5566",
            is_active=True,
        )
        url = reverse("console-org-menu-item-package-create", args=[self.item.pk])
        plu = self.client.post(
            url,
            {
                "name": "PLU pack",
                "units_per_package": "2",
                "barcode": "5566",
                "sku_alias": "",
                "sell_price": "",
                "is_sellable": "on",
                "is_purchasable": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(plu.status_code, 200)
        self.assertContains(plu, "already used by an active product PLU")

        same = self.client.post(
            url,
            {
                "name": "Same-code pack",
                "units_per_package": "2",
                "barcode": "PACK-SAME",
                "sku_alias": "pack-same",
                "sell_price": "",
                "is_sellable": "on",
                "is_purchasable": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(same.status_code, 200)
        self.assertContains(same, "Package barcode and SKU alias must be different")
        self.assertFalse(ProductPackage.objects.filter(tenant=self.tenant).exists())
