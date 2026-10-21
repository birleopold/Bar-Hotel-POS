"""Regression coverage for platform workspace onboarding and control-plane flows.

These paths previously returned 500 with production PostgreSQL RLS enabled.
SQLite exercises view behavior; production RLS must also be checked with the
non-owner PostgreSQL application role before release certification.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.tenants.models import Tenant, TenantDomain, TenantSettings


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TENANT_CENTRAL_HOSTS=["testserver"],
    TENANT_PLATFORM_DOMAIN="pos.example.test",
)
class PlatformWorkspaceLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="platform-operator@example.test", password="test-password-safe"
        )
        self.client.force_login(self.user)

    def test_create_workspace_initializes_settings_and_platform_domain(self):
        url = reverse("console-platform-tenant-create")
        response = self.client.post(
            url, {"name": "Example Grocery", "slug": "example-grocery", "is_active": "on"}
        )
        self.assertRedirects(response, reverse("console-platform-tenants"))
        tenant = Tenant.objects.get(slug="example-grocery")
        self.assertTrue(TenantSettings.objects.filter(tenant=tenant).exists())
        self.assertTrue(
            TenantDomain.objects.filter(
                tenant=tenant,
                hostname="example-grocery.pos.example.test",
                status=TenantDomain.Status.ACTIVE,
            ).exists()
        )

    def test_control_plane_loads_and_can_create_platform_domain(self):
        tenant = Tenant.objects.create(name="Example Retail", slug="example-retail")
        TenantSettings.objects.create(tenant=tenant)
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(
            self.client.post(url, {"create_platform_domain": "1"}), url
        )
        self.assertTrue(TenantDomain.objects.filter(tenant=tenant).exists())

    def test_platform_can_create_tenant_owner_without_platform_privileges(self):
        from apps.accounts.models import Membership, MembershipRole
        from apps.tenants.models import Site
        tenant = Tenant.objects.create(name="Example Grocery", slug="owner-grocery")
        site = Site.objects.create(tenant=tenant, name="Main")
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        response = self.client.post(url, {
            "create_tenant_owner": "1",
            "email": "owner@example.test",
            "password": "A-different-strong-password-391!",
            "confirm_password": "A-different-strong-password-391!",
        })
        self.assertRedirects(response, url)
        owner = get_user_model().objects.get(email="owner@example.test")
        self.assertTrue(owner.check_password("A-different-strong-password-391!"))
        self.assertFalse(owner.is_superuser)
        self.assertFalse(owner.is_platform_staff)
        membership = Membership.objects.get(user=owner, tenant=tenant)
        self.assertEqual(membership.role, MembershipRole.OWNER)
        self.assertTrue(membership.sites.filter(pk=site.pk).exists())

    def test_platform_cannot_overwrite_existing_user_password(self):
        tenant = Tenant.objects.create(name="Other Grocery", slug="other-grocery")
        existing = get_user_model().objects.create_user(
            email="existing@example.test", password="OriginalPassword904!"
        )
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        response = self.client.post(url, {
            "create_tenant_owner": "1",
            "email": existing.email,
            "password": "NewPassword904!",
            "confirm_password": "NewPassword904!",
        })
        self.assertEqual(response.status_code, 200)
        existing.refresh_from_db()
        self.assertTrue(existing.check_password("OriginalPassword904!"))
        self.assertFalse(existing.memberships.filter(tenant=tenant).exists())

    def test_normal_staff_cannot_access_platform_control_plane(self):
        other = get_user_model().objects.create_user(
            email="ordinary@example.test", password="test-password-safe"
        )
        tenant = Tenant.objects.create(name="Private", slug="private")
        self.client.force_login(other)
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TenantSettings.objects.filter(tenant=tenant).exists())
