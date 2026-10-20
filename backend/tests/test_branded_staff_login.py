"""Regression coverage for branded tenant authentication boundaries."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core import signing
from apps.staff.terminal import TERMINAL_COOKIE, TERMINAL_SALT
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.staff.forms.workspace_forms import StaffTenantBrandingForm
from apps.staff.terminal import available_workers, set_member_pin, verify_member_pin
from apps.staff.services.presentation import staff_product_presentation
from apps.tenants.models import Tenant, TenantSettings, TenantDomain, Site, Outlet, OutletType


@override_settings(ALLOWED_HOSTS=["testserver", "sennana.example.test", "kartel.example.test"])
class BrandedStaffLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.sennana = Tenant.objects.create(name="Sennana Supermarket", slug="sennana")
        self.kartel = Tenant.objects.create(name="Kartel Bar", slug="kartel")
        TenantDomain.objects.create(tenant=self.sennana, hostname="sennana.example.test",
                                    kind=TenantDomain.Kind.CUSTOM, status=TenantDomain.Status.ACTIVE)
        TenantDomain.objects.create(tenant=self.kartel, hostname="kartel.example.test",
                                    kind=TenantDomain.Kind.CUSTOM, status=TenantDomain.Status.ACTIVE)
        self.user = get_user_model().objects.create_user(
            email="kartel-worker@example.test", password="TestPassword!123"
        )
        Membership.objects.create(
            tenant=self.kartel, user=self.user, role=MembershipRole.BARTENDER
        )
        TenantSettings.objects.create(tenant=self.sennana, theme_primary="#135C49")
        TenantSettings.objects.create(tenant=self.kartel)

    def test_other_tenant_worker_cannot_sign_in_through_branded_host(self):
        response = self.client.post(
            reverse("staff-login"),
            {"username": self.user.email, "password": "TestPassword!123"},
            HTTP_HOST="sennana.example.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_worker_lookup_and_pin_are_strictly_tenant_scoped(self):
        member = Membership.objects.get(tenant=self.kartel, user=self.user)
        set_member_pin(member, "627941")
        self.assertNotIn(member, available_workers(self.sennana.pk, ""))
        self.assertIn(member, available_workers(self.kartel.pk, ""))
        self.assertIsNone(verify_member_pin(
            member_id=member.pk, tenant_id=self.sennana.pk, outlet_id="", pin="627941"
        ))
        self.assertIsNotNone(verify_member_pin(
            member_id=member.pk, tenant_id=self.kartel.pk, outlet_id="", pin="627941"
        ))

    def test_disabled_membership_is_not_available_for_pin(self):
        member = Membership.objects.get(tenant=self.kartel, user=self.user)
        set_member_pin(member, "627941")
        member.is_active = False
        member.save(update_fields=["is_active"])
        self.assertNotIn(member, available_workers(self.kartel.pk, ""))
        self.assertIsNone(verify_member_pin(
            member_id=member.pk, tenant_id=self.kartel.pk, outlet_id="", pin="627941"
        ))

    def test_branch_assigned_worker_cannot_unlock_another_branch(self):
        first_site = Site.objects.create(tenant=self.sennana, name="Main Branch")
        other_site = Site.objects.create(tenant=self.sennana, name="Second Branch")
        first_outlet = Outlet.objects.create(site=first_site, name="Till 1", outlet_type=OutletType.SUPERMARKET)
        other_outlet = Outlet.objects.create(site=other_site, name="Till 2", outlet_type=OutletType.SUPERMARKET)
        user = get_user_model().objects.create_user(email="sennana-cashier@example.test", password="TestPassword!123")
        member = Membership.objects.create(tenant=self.sennana, user=user, role=MembershipRole.SERVER)
        member.sites.add(first_site)
        set_member_pin(member, "749182")
        self.assertIn(member, available_workers(self.sennana.pk, str(first_outlet.pk)))
        self.assertNotIn(member, available_workers(self.sennana.pk, str(other_outlet.pk)))
        self.assertIsNone(verify_member_pin(
            member_id=member.pk, tenant_id=self.sennana.pk,
            outlet_id=str(other_outlet.pk), pin="749182",
        ))
        self.assertIsNotNone(verify_member_pin(
            member_id=member.pk, tenant_id=self.sennana.pk,
            outlet_id=str(first_outlet.pk), pin="749182",
        ))

    def test_branded_login_shows_only_domain_identity(self):
        response = self.client.get(
            reverse("staff-login"), HTTP_HOST="sennana.example.test"
        )
        self.assertContains(response, "Sennana Supermarket")
        self.assertNotContains(response, "Kartel Bar")


    def test_branded_workspace_sets_own_page_identity(self):
        response = self.client.get(reverse("staff-login"), HTTP_HOST="sennana.example.test")
        self.assertContains(response, "<title>Sennana Supermarket · Staff sign in</title>", html=False)
        self.assertContains(response, "PRIVATE STAFF WORKSPACE")
        self.assertContains(response, 'name="theme-color" content="#135C49"')
        self.assertNotContains(response, "Kartel Bar")

    def test_other_tenant_terminal_cookie_cannot_cross_branded_domain(self):
        member = Membership.objects.get(tenant=self.kartel, user=self.user)
        set_member_pin(member, "627941")
        self.client.cookies[TERMINAL_COOKIE] = signing.dumps(
            {"tenant": str(self.kartel.pk), "outlet": ""}, salt=TERMINAL_SALT
        )
        page = self.client.get(reverse("staff-terminal"), HTTP_HOST="sennana.example.test")
        # The domain resolver can deny a mismatched signed terminal scope
        # before the PIN view renders. A 404 is the correct fail-closed result.
        self.assertEqual(page.status_code, 404)
        self.assertNotIn(self.user.email.encode(), page.content)
        rejected = self.client.post(reverse("staff-terminal"), {
            "worker": str(member.pk), "pin": "627941",
        }, HTTP_HOST="sennana.example.test")
        self.assertEqual(rejected.status_code, 404)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_tampered_terminal_cookie_does_not_unlock_worker(self):
        member = Membership.objects.get(tenant=self.kartel, user=self.user)
        set_member_pin(member, "627941")
        signed = signing.dumps({"tenant": str(self.kartel.pk), "outlet": ""}, salt=TERMINAL_SALT)
        self.client.cookies[TERMINAL_COOKIE] = signed + "tampered"
        response = self.client.post(reverse("staff-terminal"), {
            "worker": str(member.pk), "pin": "627941",
        }, HTTP_HOST="kartel.example.test")
        self.assertRedirects(response, reverse("staff-login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_terminal_without_pairing_never_reveals_other_tenant_staff(self):
        response = self.client.get(reverse("staff-terminal"), HTTP_HOST="sennana.example.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sennana Supermarket · STAFF TERMINAL")
        self.assertNotContains(response, self.user.email)
        self.assertNotContains(response, "Kartel Bar")


class BusinessNameBrandingFormTests(TestCase):
    def test_business_name_is_required_and_normalized(self):
        tenant = Tenant.objects.create(name="Original Store", slug="original-store")
        settings = TenantSettings.objects.create(tenant=tenant)
        base_data = {
            "default_currency": settings.default_currency,
            "default_timezone": settings.default_timezone,
            "loyalty_spend_per_point": str(settings.loyalty_spend_per_point),
            "receipt_footer": "",
            "theme_primary": settings.theme_primary,
            "theme_secondary": settings.theme_secondary,
            "theme_accent": settings.theme_accent,
            "logo_url": "",
        }
        missing = StaffTenantBrandingForm(data=base_data, instance=settings)
        self.assertFalse(missing.is_valid())
        self.assertIn("business_name", missing.errors)
        form = StaffTenantBrandingForm(data={**base_data, "business_name": "  Sennana   Supermarket  "}, instance=settings)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["business_name"], "Sennana Supermarket")


class TenantSpecificPresentationTests(TestCase):
    def test_independent_retail_and_hospitality_labels(self):
        expected = (
            ("retail", "Sales", "New sale"),
            ("supermarket", "Sales", "New sale"),
            ("bar", "Orders", "New order"),
            ("lodging", "Orders", "New order"),
        )
        for line, orders_label, quick_action in expected:
            with self.subTest(line=line):
                tenant = Tenant.objects.create(name=f"{line} Example", slug=f"brand-{line}")
                TenantSettings.objects.create(tenant=tenant, business_lines=[line])
                product = staff_product_presentation(tenant)
                self.assertEqual(product["business_key"], line)
                self.assertEqual(product["orders_label"], orders_label)
                self.assertEqual(
                    "New sale" if product["business_key"] in {"retail", "supermarket"} else "New order",
                    quick_action,
                )
        bar = Tenant.objects.get(slug="brand-bar")
        self.assertEqual(staff_product_presentation(bar)["preparation_label"], "Drink prep")
        hotel = Tenant.objects.get(slug="brand-lodging")
        self.assertEqual(staff_product_presentation(hotel)["lodging_label"], "Front desk")
