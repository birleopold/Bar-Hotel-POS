from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, ProductPackage
from apps.purchasing.models import Supplier, SupplierProductCode
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

