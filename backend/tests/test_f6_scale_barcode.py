"""Opt-in weighed-product barcode safety and cashier integration."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, SupermarketSkuProfile, UnitOfMeasure
from apps.catalog.scale_labels import (
    configure_scale_weight_label, decode_scale_weight_label, ean13_check_digit,
    make_scale_weight_label,
)
from apps.pos.models import Order
from apps.pos.services.orders import add_supermarket_line_by_code
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class VariableWeightLabelTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Scale Grocery", slug="f6-scale-grocery")
        TenantSettings.objects.create(tenant=self.tenant, business_lines=["supermarket"], default_currency="UGX")
        self.site = Site.objects.create(tenant=self.tenant, name="Weighing counter")
        self.outlet = Outlet.objects.create(site=self.site, name="Retail", outlet_type=OutletType.SUPERMARKET)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Produce")
        self.item = MenuItem.objects.create(
            tenant=self.tenant, category=self.category, name="Loose rice",
            unit_price=Decimal("5000.00"), unit_of_measure=UnitOfMeasure.KG,
            track_inventory=True, is_active=True,
        )
        self.user = User.objects.create_user(email="f6-scale-owner@example.test", password="Password123!")
        self.membership = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OWNER,
        )
        self.membership.sites.add(self.site)
        self.membership.outlets.add(self.outlet)
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def configure(self, item=None, prefix="21", item_code="00123", membership=None):
        return configure_scale_weight_label(
            tenant_id=self.tenant.pk, menu_item_id=(item or self.item).pk,
            prefix=prefix, item_code=item_code,
            membership=membership or self.membership, user=self.user,
        )

    def test_ean13_weight_label_is_read_and_priced_by_kilogram(self):
        self.configure()
        barcode = make_scale_weight_label(prefix="21", item_code="00123", grams=1250)
        self.assertEqual(len(barcode), 13)
        self.assertEqual(barcode[-1], ean13_check_digit(barcode[:12]))
        item, kilograms = decode_scale_weight_label(
            tenant_id=self.tenant.pk, outlet_id=self.outlet.pk, code=barcode,
        )
        self.assertEqual(item.pk, self.item.pk)
        self.assertEqual(kilograms, Decimal("1.250"))
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, currency="UGX")
        line = add_supermarket_line_by_code(order=order, code=barcode, quantity=Decimal("1"), user=self.user)
        self.assertEqual(line.quantity, Decimal("1.250"))
        self.assertEqual(line.line_total, Decimal("6250.00"))
        self.assertEqual(line.pricing_source, "weighted")
        with self.assertRaisesRegex(ValidationError, "quantity at 1"):
            add_supermarket_line_by_code(order=order, code=barcode, quantity=Decimal("2"), user=self.user)
        self.assertEqual(order.lines.count(), 1)

    def test_bad_checksum_and_zero_weight_cannot_add_item(self):
        self.configure()
        valid = make_scale_weight_label(prefix="21", item_code="00123", grams=420)
        invalid = valid[:-1] + ("0" if valid[-1] != "0" else "1")
        with self.assertRaisesRegex(ValidationError, "checksum"):
            decode_scale_weight_label(tenant_id=self.tenant.pk, outlet_id=self.outlet.pk, code=invalid)
        zero_body = "210012300000"
        zero = zero_body + ean13_check_digit(zero_body)
        with self.assertRaisesRegex(ValidationError, "positive net weight"):
            decode_scale_weight_label(tenant_id=self.tenant.pk, outlet_id=self.outlet.pk, code=zero)
        self.assertIsNone(decode_scale_weight_label(
            tenant_id=self.tenant.pk, outlet_id=self.outlet.pk,
            code=make_scale_weight_label(prefix="22", item_code="00123", grams=500),
        ))
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, currency="UGX")
        with self.assertRaises(ValidationError):
            add_supermarket_line_by_code(order=order, code=invalid, quantity=Decimal("1"), user=self.user)
        self.assertEqual(order.lines.count(), 0)

    def test_configurations_are_opt_in_unique_and_idempotent(self):
        first, replay = self.configure()
        same, repeated = self.configure()
        self.assertFalse(replay)
        self.assertTrue(repeated)
        self.assertEqual(first.pk, same.pk)
        self.assertTrue(first.allow_fractional_quantity)
        self.assertFalse(first.sell_by_unit)
        other = MenuItem.objects.create(
            tenant=self.tenant, category=self.category, name="Loose beans",
            unit_price=Decimal("3500"), unit_of_measure=UnitOfMeasure.KG,
            track_inventory=True,
        )
        with self.assertRaisesRegex(ValidationError, "already assigned"):
            self.configure(item=other)
        with self.assertRaises(ValidationError):
            self.configure(item_code="ABC12")
        with self.assertRaises(ValidationError):
            self.configure(prefix="30", item_code="00124")
        self.assertEqual(SupermarketSkuProfile.objects.filter(scale_prefix="21").count(), 1)
        profile, cleared = self.configure(prefix="", item_code="")
        self.assertFalse(cleared)
        self.assertEqual(profile.scale_prefix, "")

    def test_non_admin_and_wrong_unit_rejected(self):
        self.membership.role = MembershipRole.OUTLET_MANAGER
        self.membership.save(update_fields=["role"])
        with self.assertRaisesRegex(ValidationError, "owner or administrator"):
            self.configure()
        self.membership.role = MembershipRole.OWNER
        self.membership.save(update_fields=["role"])
        item = MenuItem.objects.create(
            tenant=self.tenant, category=self.category, name="Bottled juice",
            unit_price=Decimal("3000"), unit_of_measure=UnitOfMeasure.EACH,
            track_inventory=True,
        )
        with self.assertRaisesRegex(ValidationError, "kilogram"):
            self.configure(item=item)

    def test_owner_staff_screen_configures_a_real_product(self):
        url = reverse("staff-inventory-scale-labels")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loose rice")
        self.assertContains(response, "exact format")
        result = self.client.post(url, {
            "menu_item_id": str(self.item.pk),
            "scale_prefix": "21", "scale_item_code": "00123",
        })
        self.assertEqual(result.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.supermarket_profile.scale_prefix, "21")
        self.assertEqual(self.item.supermarket_profile.scale_item_code, "00123")
