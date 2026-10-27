from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, ProductFamily, ProductLabelQueueEntry
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class VariantMaintenanceGridTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Variant maintenance", slug="variant-maintenance")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["inventory", "pos"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Retail", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="variant-maintenance@test.local", password="Password9!")
        membership = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OWNER,
        )
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Clothing")
        self.family = ProductFamily.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Polo Shirt",
            variant_schema=[{"name": "Colour", "values": ["Black", "White"]}],
        )
        self.black = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            product_family=self.family,
            variant_key="black-key",
            variant_values={"Colour": "Black"},
            name="Polo Shirt · Black",
            sku="POLO-BLACK",
            barcode="POLO-BLACK-BC",
            unit_price=Decimal("45000"),
            reorder_level=Decimal("4"),
            track_inventory=True,
            is_active=True,
        )
        self.white = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            product_family=self.family,
            variant_key="white-key",
            variant_values={"Colour": "White"},
            name="Polo Shirt · White",
            sku="POLO-WHITE",
            barcode="POLO-WHITE-BC",
            unit_price=Decimal("45000"),
            reorder_level=Decimal("4"),
            track_inventory=True,
            is_active=True,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session.save()

    def _payload(self):
        return {
            "action": "update_existing",
            f"variant-{self.black.pk}-unit_price": "48000",
            f"variant-{self.black.pk}-reorder_level": "6",
            f"variant-{self.black.pk}-is_active": "on",
            f"variant-{self.white.pk}-unit_price": "45000",
            f"variant-{self.white.pk}-reorder_level": "2",
        }

    def test_matrix_page_exposes_bulk_variant_maintenance_grid(self):
        response = self.client.get(
            reverse("console-org-product-family-matrix", args=[self.family.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save variant changes")
        self.assertContains(response, f'variant-{self.black.pk}-unit_price')
        self.assertContains(response, f'variant-{self.white.pk}-reorder_level')
        self.assertContains(response, "SKU, barcode and variant dimensions stay protected")

    def test_bulk_variant_update_changes_commercial_fields_only(self):
        url = reverse("console-org-product-family-matrix", args=[self.family.pk])
        original_black_identity = (
            self.black.sku, self.black.barcode, dict(self.black.variant_values), self.black.variant_key
        )
        original_white_identity = (
            self.white.sku, self.white.barcode, dict(self.white.variant_values), self.white.variant_key
        )
        response = self.client.post(url, self._payload())
        self.assertEqual(response.status_code, 302)

        self.black.refresh_from_db()
        self.white.refresh_from_db()
        self.assertEqual(self.black.unit_price, Decimal("48000.00"))
        self.assertEqual(self.black.reorder_level, Decimal("6"))
        self.assertTrue(self.black.is_active)
        self.assertEqual(self.white.unit_price, Decimal("45000.00"))
        self.assertEqual(self.white.reorder_level, Decimal("2"))
        self.assertFalse(self.white.is_active)
        self.assertEqual(
            (self.black.sku, self.black.barcode, self.black.variant_values, self.black.variant_key),
            original_black_identity,
        )
        self.assertEqual(
            (self.white.sku, self.white.barcode, self.white.variant_values, self.white.variant_key),
            original_white_identity,
        )

    def test_price_change_queues_label_for_active_variant_only(self):
        url = reverse("console-org-product-family-matrix", args=[self.family.pk])
        response = self.client.post(url, self._payload())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ProductLabelQueueEntry.objects.filter(
                tenant=self.tenant,
                outlet=self.outlet,
                menu_item=self.black,
                reason=ProductLabelQueueEntry.Reason.PRICE_CHANGE,
                status=ProductLabelQueueEntry.Status.PENDING,
            ).exists()
        )
        self.assertFalse(
            ProductLabelQueueEntry.objects.filter(
                tenant=self.tenant,
                outlet=self.outlet,
                menu_item=self.white,
                reason=ProductLabelQueueEntry.Reason.PRICE_CHANGE,
            ).exists()
        )

    def test_invalid_row_rolls_back_all_variant_changes(self):
        url = reverse("console-org-product-family-matrix", args=[self.family.pk])
        payload = self._payload()
        payload[f"variant-{self.white.pk}-unit_price"] = "-1"
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ensure this value is greater than or equal to 0")
        self.black.refresh_from_db()
        self.white.refresh_from_db()
        self.assertEqual(self.black.unit_price, Decimal("45000.00"))
        self.assertEqual(self.black.reorder_level, Decimal("4"))
        self.assertEqual(self.white.unit_price, Decimal("45000.00"))
        self.assertEqual(self.white.reorder_level, Decimal("4"))
