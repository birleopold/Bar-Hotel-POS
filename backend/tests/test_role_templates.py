from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, RoleTemplate, User
from apps.audit.models import AuditEvent
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_KEY,
    STAFF_SESSION_SITE_KEY,
    STAFF_SESSION_TENANT_KEY,
)
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class RoleTemplateWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Role Templates", slug="role-template-tests")
        TenantSettings.objects.update_or_create(
            tenant=cls.tenant,
            defaults={"business_lines": ["supermarket"]},
        )
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main branch")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Checkout",
            outlet_type=OutletType.SUPERMARKET,
        )
        cls.owner = User.objects.create_user(
            email="roles-owner@test.local",
            password="Password9!",
        )
        cls.owner_membership = Membership.objects.create(
            tenant=cls.tenant,
            user=cls.owner,
            role=MembershipRole.OWNER,
        )

        cls.foreign = Tenant.objects.create(name="Foreign Roles", slug="foreign-role-template-tests")
        TenantSettings.objects.update_or_create(
            tenant=cls.foreign,
            defaults={"business_lines": ["supermarket"]},
        )
        foreign_site = Site.objects.create(tenant=cls.foreign, name="Foreign")
        cls.foreign_outlet = Outlet.objects.create(
            site=foreign_site,
            name="Foreign checkout",
            outlet_type=OutletType.SUPERMARKET,
        )
        cls.foreign_template = RoleTemplate.objects.create(
            tenant=cls.foreign,
            name="Foreign cashier",
            base_role=MembershipRole.SERVER,
        )
        cls.foreign_template.sites.add(foreign_site)
        cls.foreign_template.outlets.add(cls.foreign_outlet)

    def login(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_SITE_KEY] = str(self.site.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_role_directory_previews_only_permitted_business_roles(self):
        self.login()
        response = self.client.get(reverse("staff-workspace-role-templates"))
        self.assertEqual(response.status_code, 200)
        labels = {row["role_label"] for row in response.context["built_in_role_previews"]}
        self.assertIn("Server / floor", labels)
        self.assertIn("Storekeeper", labels)
        self.assertNotIn("Bartender", labels)
        self.assertContains(response, "Roles & access")
        self.assertContains(response, "Templates never create owner/admin access")

    def test_create_apply_edit_and_reapply_template(self):
        self.login()
        create = self.client.post(
            reverse("staff-workspace-role-template-create"),
            {
                "name": "Main Shop Cashier",
                "description": "Checkout team for the main shop",
                "base_role": MembershipRole.SERVER,
                "is_active": "on",
                "sites": [str(self.site.pk)],
                "outlets": [str(self.outlet.pk)],
            },
        )
        self.assertEqual(create.status_code, 302)
        template = RoleTemplate.objects.get(
            tenant=self.tenant,
            name="Main Shop Cashier",
        )
        self.assertEqual(template.base_role, MembershipRole.SERVER)
        self.assertEqual(set(template.sites.all()), {self.site})
        self.assertEqual(set(template.outlets.all()), {self.outlet})
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action="workspace.role_template.created",
                entity_id=str(template.pk),
            ).exists()
        )

        worker_create = self.client.post(
            reverse("staff-workspace-member-create"),
            {
                "first_name": "Cash",
                "last_name": "Worker",
                "email": "templated-worker@test.local",
                "phone": "",
                "role_preset": "",
                "role_template": str(template.pk),
                "role": MembershipRole.SERVER,
                "sites": [],
                "outlets": [],
                "send_reset_link": "on",
            },
        )
        self.assertEqual(worker_create.status_code, 302)
        worker = Membership.objects.get(
            tenant=self.tenant,
            user__email="templated-worker@test.local",
        )
        self.assertEqual(worker.role, MembershipRole.SERVER)
        self.assertEqual(worker.role_template_id, template.pk)
        self.assertEqual(set(worker.sites.all()), {self.site})
        self.assertEqual(set(worker.outlets.all()), {self.outlet})

        edit = self.client.post(
            reverse(
                "staff-workspace-role-template-edit",
                kwargs={"template_id": template.pk},
            ),
            {
                "name": "Main Shop Stock",
                "description": "Stock team for the main shop",
                "base_role": MembershipRole.STOREKEEPER,
                "is_active": "on",
                "sites": [str(self.site.pk)],
                "outlets": [str(self.outlet.pk)],
            },
        )
        self.assertEqual(edit.status_code, 302)
        template.refresh_from_db()
        worker.refresh_from_db()
        self.assertEqual(template.base_role, MembershipRole.STOREKEEPER)
        self.assertEqual(worker.role, MembershipRole.SERVER)
        self.assertEqual(worker.role_template_id, template.pk)

        bulk = self.client.post(
            reverse("staff-workspace-member-bulk-action"),
            {
                "member_ids": [str(worker.pk)],
                "action": "apply_template",
                "role_preset": "",
                "role_template": str(template.pk),
            },
        )
        self.assertEqual(bulk.status_code, 302)
        worker.refresh_from_db()
        self.assertEqual(worker.role, MembershipRole.STOREKEEPER)
        self.assertEqual(worker.role_template_id, template.pk)
        self.assertEqual(set(worker.sites.all()), {self.site})
        self.assertEqual(set(worker.outlets.all()), {self.outlet})

    def test_template_cannot_cross_tenant_or_package_admin_access(self):
        self.login()
        response = self.client.post(
            reverse("staff-workspace-member-create"),
            {
                "email": "cross-tenant@test.local",
                "role_preset": "",
                "role_template": str(self.foreign_template.pk),
                "role": MembershipRole.SERVER,
                "sites": [],
                "outlets": [],
                "send_reset_link": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(
            Membership.objects.filter(
                tenant=self.tenant,
                user__email="cross-tenant@test.local",
            ).exists()
        )

        response = self.client.post(
            reverse("staff-workspace-role-template-create"),
            {
                "name": "Hidden admin",
                "description": "",
                "base_role": MembershipRole.TENANT_ADMIN,
                "is_active": "on",
                "sites": [str(self.site.pk)],
                "outlets": [str(self.outlet.pk)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(
            RoleTemplate.objects.filter(
                tenant=self.tenant,
                name="Hidden admin",
            ).exists()
        )

    def test_builtin_preset_and_saved_template_are_mutually_exclusive(self):
        self.login()
        template = RoleTemplate.objects.create(
            tenant=self.tenant,
            name="Cashier template",
            base_role=MembershipRole.SERVER,
        )
        template.sites.add(self.site)
        template.outlets.add(self.outlet)
        response = self.client.post(
            reverse("staff-workspace-member-create"),
            {
                "email": "ambiguous-role@test.local",
                "role_preset": "cashier",
                "role_template": str(template.pk),
                "role": MembershipRole.SERVER,
                "sites": [str(self.site.pk)],
                "outlets": [str(self.outlet.pk)],
                "send_reset_link": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Choose either a built-in role preset or a saved role template",
            response.content.decode(),
        )
