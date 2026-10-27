from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, ProductPackage
from apps.inventory.models import StockBalance
from apps.purchasing.models import Supplier, SupplierPriceRecord, SupplierProductCode
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class SupplierProductCodeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Supplier codes", slug="supplier-codes")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["purchasing", "inventory", "pos"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Store", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="supplier-codes@test.local", password="Password9!")
        membership = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OWNER,
        )
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="General")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Mineral water",
            sku="WATER-500",
            unit_price=Decimal("1000"),
            track_inventory=True,
        )
        self.package = ProductPackage.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            name="Case of 24",
            units_per_package=Decimal("24"),
            is_purchasable=True,
            is_sellable=True,
        )
        self.supplier = Supplier.objects.create(tenant=self.tenant, name="Water vendor")
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_owner_can_map_supplier_code_to_existing_package(self):
        url = reverse("staff-purchasing-supplier-codes", args=[self.supplier.pk])
        response = self.client.post(
            url,
            {
                "action": "save",
                "menu_item": str(self.item.pk),
                "product_package": str(self.package.pk),
                "code": "VENDOR-WATER-24",
                "description": "Vendor carton code",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        mapping = SupplierProductCode.objects.get(
            tenant=self.tenant, supplier=self.supplier, code="VENDOR-WATER-24",
        )
        self.assertEqual(mapping.menu_item, self.item)
        self.assertEqual(mapping.product_package, self.package)

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "VENDOR-WATER-24")
        self.assertContains(page, "Case of 24")

    def test_supplier_code_must_use_package_from_selected_product(self):
        other = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Juice",
            sku="JUICE-1",
            unit_price=Decimal("2000"),
            track_inventory=True,
        )
        url = reverse("staff-purchasing-supplier-codes", args=[self.supplier.pk])
        response = self.client.post(
            url,
            {
                "action": "save",
                "menu_item": str(other.pk),
                "product_package": str(self.package.pk),
                "code": "BAD-MAP",
                "description": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Choose a package that belongs to the selected product.", status_code=400)
        self.assertFalse(SupplierProductCode.objects.filter(code="BAD-MAP").exists())

    def test_same_supplier_code_is_case_insensitively_unique(self):
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            code="Vendor-ABC",
        )
        url = reverse("staff-purchasing-supplier-codes", args=[self.supplier.pk])
        response = self.client.post(
            url,
            {
                "action": "save",
                "menu_item": str(self.item.pk),
                "product_package": "",
                "code": "vendor-abc",
                "description": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "This supplier code is already in use.", status_code=400)
        self.assertEqual(SupplierProductCode.objects.filter(supplier=self.supplier).count(), 1)

    def test_purchase_order_package_choice_shows_selected_supplier_code(self):
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            product_package=self.package,
            code="SUP-CASE-24",
        )
        response = self.client.get(
            reverse("staff-purchasing-order-create"),
            {"supplier": str(self.supplier.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "supplier code SUP-CASE-24")

    def test_supplier_code_does_not_become_cashier_barcode(self):
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            product_package=self.package,
            code="PURCHASE-ONLY-24",
        )
        from apps.pos.services import lookup_supermarket_sellable_for_code
        item, source, package = lookup_supermarket_sellable_for_code(
            tenant_id=self.tenant.pk,
            outlet_id=self.outlet.pk,
            code="PURCHASE-ONLY-24",
        )
        self.assertIsNone(item)
        self.assertEqual(source, "")
        self.assertIsNone(package)

    def test_other_tenant_supplier_code_page_is_not_exposed(self):
        other = Tenant.objects.create(name="Other supplier tenant", slug="other-supplier-tenant")
        TenantSettings.objects.create(tenant=other, business_lines=["supermarket"])
        other_supplier = Supplier.objects.create(tenant=other, name="Other vendor")
        response = self.client.get(
            reverse("staff-purchasing-supplier-codes", args=[other_supplier.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("staff-purchasing-suppliers"))

    def test_only_one_preferred_supplier_can_be_assigned_per_product(self):
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            code="PREF-ONE",
            default_unit_cost=Decimal("700"),
            is_preferred=True,
        )
        second = Supplier.objects.create(
            tenant=self.tenant,
            name="Second water vendor",
        )
        url = reverse("staff-purchasing-supplier-codes", args=[second.pk])
        response = self.client.post(
            url,
            {
                "action": "save",
                "menu_item": str(self.item.pk),
                "product_package": "",
                "code": "PREF-TWO",
                "description": "",
                "default_unit_cost": "680",
                "is_preferred": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Another supplier is already preferred for this product",
            status_code=400,
        )
        self.assertFalse(
            SupplierProductCode.objects.filter(
                supplier=second,
                menu_item=self.item,
                is_preferred=True,
            ).exists()
        )



    def test_supplier_price_csv_preview_apply_preserves_inventory_and_retail_price(self):
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            product_package=self.package,
            code="SUP-CASE-24",
        )
        StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.item,
            quantity=Decimal("12"),
            average_unit_cost=Decimal("650.0000"),
            cost_basis_complete=True,
        )
        url = reverse(
            "staff-purchasing-supplier-codes",
            args=[self.supplier.pk],
        )
        body = (
            "supplier_code,sku,unit_cost,minimum_quantity,valid_from,valid_until,source_reference,note\n"
            "SUP-CASE-24,,600,24,2026-11-01,2026-12-31,NOV-CATALOG,Case contract\n"
            ",WATER-500,640,1,2027-01-01,,JAN-CATALOG,Base price\n"
        )
        preview = self.client.post(
            url,
            {
                "action": "price_import_preview",
                "price_file": SimpleUploadedFile(
                    "water-prices.csv",
                    body.encode("utf-8"),
                    content_type="text/csv",
                ),
            },
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(len(preview.context["price_import_rows"]), 2)
        token = preview.context["price_import_token"]
        self.assertTrue(token)
        self.assertContains(preview, "SUP-CASE-24")
        self.assertContains(preview, "WATER-500")

        retail_price_before = self.item.unit_price
        average_cost_before = StockBalance.objects.get(
            outlet=self.outlet,
            menu_item=self.item,
        ).average_unit_cost
        apply_response = self.client.post(
            url,
            {
                "action": "price_import_apply",
                "price_import_token": token,
            },
        )
        self.assertEqual(apply_response.status_code, 302)

        prices = SupplierPriceRecord.objects.filter(
            tenant=self.tenant,
            supplier=self.supplier,
        ).order_by("valid_from")
        self.assertEqual(prices.count(), 2)
        package_price = prices.get(source_reference="NOV-CATALOG")
        self.assertEqual(package_price.menu_item_id, self.item.pk)
        self.assertEqual(package_price.product_package_id, self.package.pk)
        self.assertEqual(package_price.unit_cost, Decimal("600.00"))
        self.assertEqual(
            package_price.minimum_quantity,
            Decimal("24.000"),
        )
        base_price = prices.get(source_reference="JAN-CATALOG")
        self.assertIsNone(base_price.product_package_id)
        self.assertEqual(base_price.unit_cost, Decimal("640.00"))

        self.item.refresh_from_db()
        balance = StockBalance.objects.get(
            outlet=self.outlet,
            menu_item=self.item,
        )
        self.assertEqual(self.item.unit_price, retail_price_before)
        self.assertEqual(balance.average_unit_cost, average_cost_before)

    def test_supplier_price_import_rejects_duplicate_rows_and_tampered_preview(self):
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            code="SUP-WATER",
        )
        url = reverse(
            "staff-purchasing-supplier-codes",
            args=[self.supplier.pk],
        )
        duplicate_body = (
            "supplier_code,unit_cost,minimum_quantity,valid_from,source_reference\n"
            "SUP-WATER,700,1,2026-11-01,CATALOG-A\n"
            "SUP-WATER,710,1,2026-11-01,CATALOG-A\n"
        )
        duplicate = self.client.post(
            url,
            {
                "action": "price_import_preview",
                "price_file": SimpleUploadedFile(
                    "duplicate.csv",
                    duplicate_body.encode("utf-8"),
                    content_type="text/csv",
                ),
            },
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertContains(
            duplicate,
            "duplicate price target in this CSV",
            status_code=400,
        )
        self.assertFalse(
            SupplierPriceRecord.objects.filter(
                tenant=self.tenant,
                supplier=self.supplier,
            ).exists()
        )

        valid_body = (
            "supplier_code,unit_cost,source_reference\n"
            "SUP-WATER,700,CATALOG-B\n"
        )
        preview = self.client.post(
            url,
            {
                "action": "price_import_preview",
                "price_file": SimpleUploadedFile(
                    "valid.csv",
                    valid_body.encode("utf-8"),
                    content_type="text/csv",
                ),
            },
        )
        token = preview.context["price_import_token"]
        tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
        response = self.client.post(
            url,
            {
                "action": "price_import_apply",
                "price_import_token": tampered,
            },
            follow=True,
        )
        self.assertContains(
            response,
            "preview expired or was altered",
        )
        self.assertFalse(
            SupplierPriceRecord.objects.filter(
                tenant=self.tenant,
                supplier=self.supplier,
            ).exists()
        )

    def test_supplier_price_import_cannot_match_other_tenant_sku(self):
        other = Tenant.objects.create(
            name="Foreign price tenant",
            slug="foreign-price-tenant",
        )
        TenantSettings.objects.create(
            tenant=other,
            business_lines=["supermarket"],
        )
        other_category = MenuCategory.objects.create(
            tenant=other,
            name="Private",
        )
        MenuItem.objects.create(
            tenant=other,
            category=other_category,
            name="Private item",
            sku="FOREIGN-ONLY",
            unit_price=Decimal("1"),
            track_inventory=True,
        )
        url = reverse(
            "staff-purchasing-supplier-codes",
            args=[self.supplier.pk],
        )
        body = "sku,unit_cost\nFOREIGN-ONLY,10\n"
        response = self.client.post(
            url,
            {
                "action": "price_import_preview",
                "price_file": SimpleUploadedFile(
                    "foreign.csv",
                    body.encode("utf-8"),
                    content_type="text/csv",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "no active product matches",
            status_code=400,
        )
        self.assertFalse(
            SupplierPriceRecord.objects.filter(
                tenant=self.tenant,
                supplier=self.supplier,
            ).exists()
        )


    def test_purchase_planning_compares_supplier_evidence_without_auto_selecting(self):
        from datetime import timedelta
        from django.utils import timezone

        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            code="WATER-A",
            default_unit_cost=Decimal("700"),
            minimum_order_quantity=Decimal("1"),
            expected_lead_days=4,
            is_preferred=True,
        )
        SupplierPriceRecord.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            menu_item=self.item,
            unit_cost=Decimal("680"),
            minimum_quantity=Decimal("1"),
            valid_from=timezone.localdate() - timedelta(days=1),
            valid_until=timezone.localdate() + timedelta(days=10),
            source_reference="ACTIVE-A",
        )
        cheaper = Supplier.objects.create(
            tenant=self.tenant,
            name="Cheap but bulk vendor",
        )
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=cheaper,
            menu_item=self.item,
            code="WATER-B",
            default_unit_cost=Decimal("600"),
            minimum_order_quantity=Decimal("24"),
            expected_lead_days=2,
        )
        expired = Supplier.objects.create(
            tenant=self.tenant,
            name="Expired price vendor",
        )
        SupplierProductCode.objects.create(
            tenant=self.tenant,
            supplier=expired,
            menu_item=self.item,
            code="WATER-C",
            default_unit_cost=Decimal("690"),
            minimum_order_quantity=Decimal("1"),
        )
        SupplierPriceRecord.objects.create(
            tenant=self.tenant,
            supplier=expired,
            menu_item=self.item,
            unit_cost=Decimal("500"),
            minimum_quantity=Decimal("1"),
            valid_until=timezone.localdate() - timedelta(days=1),
            source_reference="EXPIRED-C",
        )

        response = self.client.get(
            reverse("staff-purchasing-order-create"),
            {
                "menu_item": str(self.item.pk),
                "quantity": "12",
            },
        )
        self.assertEqual(response.status_code, 200)
        options = response.context["supplier_purchase_options"]
        by_name = {row["supplier"].name: row for row in options}

        main = by_name[self.supplier.name]
        self.assertEqual(main["current_cost"], Decimal("680.00"))
        self.assertEqual(main["cost_source"], "Effective price list")
        self.assertTrue(main["preferred"])
        self.assertTrue(main["eligible"])
        self.assertTrue(main["is_lowest_cost"])

        bulk = by_name[cheaper.name]
        self.assertEqual(bulk["current_cost"], Decimal("600.00"))
        self.assertFalse(bulk["eligible"])
        self.assertFalse(bulk["is_lowest_cost"])

        fallback = by_name[expired.name]
        self.assertEqual(fallback["current_cost"], Decimal("690.00"))
        self.assertEqual(fallback["cost_source"], "Supplier planning cost")
        self.assertNotEqual(fallback["source_reference"], "EXPIRED-C")

        self.assertContains(response, "Lowest eligible planning cost")
        self.assertContains(response, "Below MOQ")
        self.assertNotContains(
            response,
            f'supplier={cheaper.pk}&amp;menu_item={self.item.pk}',
        )

    def test_supplier_comparison_is_tenant_scoped(self):
        other = Tenant.objects.create(
            name="Other supplier comparison",
            slug="other-supplier-comparison",
        )
        TenantSettings.objects.create(
            tenant=other,
            business_lines=["supermarket"],
        )
        other_category = MenuCategory.objects.create(
            tenant=other,
            name="Other goods",
        )
        other_item = MenuItem.objects.create(
            tenant=other,
            category=other_category,
            name="Foreign water",
            sku="FOREIGN-WATER",
            unit_price=Decimal("1"),
            track_inventory=True,
        )
        other_supplier = Supplier.objects.create(
            tenant=other,
            name="Foreign vendor",
        )
        SupplierProductCode.objects.create(
            tenant=other,
            supplier=other_supplier,
            menu_item=other_item,
            code="FOREIGN-CODE",
            default_unit_cost=Decimal("1"),
        )
        response = self.client.get(
            reverse("staff-purchasing-order-create"),
            {
                "menu_item": str(self.item.pk),
                "quantity": "12",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Foreign vendor")
