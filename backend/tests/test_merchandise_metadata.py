from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    ProductAlternateCode,
    ProductCustomFieldDefinition,
    ProductCustomFieldValue,
)
from apps.pos.models import Order
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class MerchandiseMetadataTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Metadata shop", slug="metadata-shop")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "inventory", "workspace"],
            default_currency="UGX",
            hardware_barcode_scanner_enabled=True,
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Checkout", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="metadata@test.local", password="Password9!")
        membership = Membership.objects.create(
            user=self.user, tenant=self.tenant, role=MembershipRole.OWNER,
        )
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Electronics")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Smart Phone",
            sku="PHONE-001",
            barcode="100200300",
            unit_price=Decimal("750000"),
            track_inventory=False,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_product_editor_saves_standard_merchandise_metadata(self):
        response = self.client.post(
            reverse("console-org-menu-item-edit", args=[self.item.pk]),
            {
                "category": str(self.category.pk),
                "product_family": "",
                "name": self.item.name,
                "description": "",
                "brand": "Acme",
                "model_number": "A100",
                "reference_code": "REF-UG-001",
                "msrp": "800000",
                "display_image_url": "",
                "sku": self.item.sku,
                "barcode": self.item.barcode,
                "unit_of_measure": "each",
                "units_per_carton": "1",
                "track_inventory": "",
                "serial_tracking": "",
                "serial_identifier_type": "serial",
                "warranty_months": "",
                "reorder_level": "",
                "unit_price": "750000",
                "tax_rate_percent": "",
                "is_active": "on",
                "kds_station": "",
                "consume_recipe_on_sale": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.brand, "Acme")
        self.assertEqual(self.item.model_number, "A100")
        self.assertEqual(self.item.reference_code, "REF-UG-001")
        self.assertEqual(self.item.msrp, Decimal("800000.00"))
        self.assertEqual(self.item.unit_price, Decimal("750000.00"))

    def test_owner_defines_custom_fields_and_saves_product_values(self):
        create = self.client.post(
            reverse("console-org-product-custom-field-create"),
            {
                "name": "Storage capacity",
                "key": "storage_capacity",
                "field_type": "text",
                "help_text": "Internal storage",
                "sort_order": "1",
                "is_active": "on",
            },
        )
        self.assertEqual(create.status_code, 302)
        definition = ProductCustomFieldDefinition.objects.get(tenant=self.tenant)
        metadata_url = reverse("console-org-menu-item-metadata", args=[self.item.pk])
        page = self.client.get(metadata_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Storage capacity")

        saved = self.client.post(
            metadata_url,
            {f"custom_{definition.pk}": "256 GB"},
        )
        self.assertEqual(saved.status_code, 302)
        value = ProductCustomFieldValue.objects.get(
            tenant=self.tenant, menu_item=self.item, definition=definition,
        )
        self.assertEqual(value.value_text, "256 GB")

    def test_inactive_custom_field_preserves_existing_value(self):
        definition = ProductCustomFieldDefinition.objects.create(
            tenant=self.tenant,
            name="Colour family",
            key="colour_family",
            field_type="text",
            is_active=True,
        )
        ProductCustomFieldValue.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            definition=definition,
            value_text="Midnight blue",
        )
        definition.is_active = False
        definition.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("console-org-menu-item-metadata", args=[self.item.pk]),
            {},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ProductCustomFieldValue.objects.get(
                tenant=self.tenant,
                menu_item=self.item,
                definition=definition,
            ).value_text,
            "Midnight blue",
        )

    def test_alternate_code_scans_same_concrete_product(self):
        code = ProductAlternateCode.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            code="SUP-ALT-001",
            code_type="supplier",
            is_active=True,
        )
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            currency="UGX",
        )
        response = self.client.post(
            reverse("staff-order-detail", args=[order.pk]),
            {
                "action": "scan_add_line",
                "code": code.code,
                "quantity": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        line = order.lines.get(is_voided=False)
        self.assertEqual(line.menu_item, self.item)
        self.assertEqual(line.quantity, Decimal("1"))
        self.assertEqual(line.pricing_source, "barcode")

    def test_catalogue_search_finds_brand_model_reference_and_alternate_code(self):
        self.item.brand = "Acme"
        self.item.model_number = "A100"
        self.item.reference_code = "REF-XYZ"
        self.item.save(update_fields=["brand", "model_number", "reference_code"])
        ProductAlternateCode.objects.create(
            tenant=self.tenant,
            menu_item=self.item,
            code="SUPPLIER-9988",
            code_type="supplier",
            is_active=True,
        )
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            currency="UGX",
        )
        url = reverse("staff-order-detail", args=[order.pk])
        for term in ("Acme", "A100", "REF-XYZ", "SUPPLIER-9988"):
            response = self.client.get(url, {"catalogue_q": term})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Smart Phone")

    def test_other_tenant_product_metadata_is_not_accessible(self):
        other = Tenant.objects.create(name="Other metadata tenant", slug="other-metadata")
        TenantSettings.objects.create(tenant=other, business_lines=["supermarket"])
        other_category = MenuCategory.objects.create(tenant=other, name="Other")
        other_item = MenuItem.objects.create(
            tenant=other,
            category=other_category,
            name="Other phone",
            unit_price=Decimal("1"),
        )
        response = self.client.get(
            reverse("console-org-menu-item-metadata", args=[other_item.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_alternate_code_cannot_reuse_primary_product_code(self):
        response = self.client.post(
            reverse("console-org-menu-item-alternate-code-create", args=[self.item.pk]),
            {
                "code": self.item.sku,
                "code_type": "internal",
                "label": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already belongs to a product barcode or SKU")
        self.assertFalse(ProductAlternateCode.objects.filter(tenant=self.tenant).exists())
