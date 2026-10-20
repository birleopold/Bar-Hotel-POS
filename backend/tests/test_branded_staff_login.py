"""Regression coverage for branded tenant authentication boundaries."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.tenants.models import Tenant, TenantSettings, TenantDomain


@override_settings(ALLOWED_HOSTS=["testserver", "sennana.example.test", "kartel.example.test"])
class BrandedStaffLoginTests(TestCase):
    def setUp(self):
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
