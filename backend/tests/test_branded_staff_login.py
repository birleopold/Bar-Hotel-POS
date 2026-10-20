"""Regression coverage for branded tenant authentication boundaries."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.staff.forms.workspace_forms import StaffTenantBrandingForm
from apps.tenants.models import Tenant, TenantSettings, TenantDomain


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
