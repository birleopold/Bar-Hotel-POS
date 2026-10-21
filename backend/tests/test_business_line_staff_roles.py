from django.test import TestCase

from apps.accounts.models import MembershipRole
from apps.accounts.role_policy import permitted_roles
from apps.staff.forms import StaffTeamInviteForm, StaffWorkerCreateForm, StaffMembershipManageForm, StaffMembershipBulkActionForm


from apps.tenants.models import Tenant, TenantSettings


class BusinessRolePolicyTests(TestCase):
    def tenant_for(self, lines):
        import uuid
        slug = "roles-" + uuid.uuid4().hex[:12]
        tenant = Tenant.objects.create(name="Roles Test", slug=slug)
        TenantSettings.objects.update_or_create(tenant=tenant, defaults={"business_lines": lines})
        return tenant
    def test_supermarket_excludes_hospitality_roles(self):
        allowed = permitted_roles(self.tenant_for(["supermarket"]))
        self.assertIn(MembershipRole.SERVER, allowed)
        self.assertIn(MembershipRole.STOREKEEPER, allowed)
        for role in (MembershipRole.BARTENDER, MembershipRole.KITCHEN, MembershipRole.CLEANER, MembershipRole.FRONT_DESK):
            self.assertNotIn(role, allowed)

    def test_hotel_roles_are_relevant(self):
        allowed = permitted_roles(self.tenant_for(["lodging"]))
        self.assertIn(MembershipRole.FRONT_DESK, allowed)
        self.assertIn(MembershipRole.CLEANER, allowed)
        self.assertNotIn(MembershipRole.BARTENDER, allowed)

    def test_mixed_businesses_have_union_of_roles(self):
        allowed = permitted_roles(self.tenant_for(["supermarket", "bar"]))
        self.assertIn(MembershipRole.BARTENDER, allowed)
        self.assertIn(MembershipRole.STOREKEEPER, allowed)

    def test_tenant_forms_hide_irrelevant_roles_and_presets(self):
        tenant = self.tenant_for(["supermarket"])
        for form_class in (StaffTeamInviteForm, StaffWorkerCreateForm):
            form = form_class(tenant=tenant)
            roles = dict(form.fields["role"].choices)
            presets = dict(form.fields["role_preset"].choices)
            self.assertNotIn(MembershipRole.BARTENDER, roles)
            self.assertNotIn("bar_staff", presets)
            self.assertIn(MembershipRole.SERVER, roles)
            self.assertIn("cashier", presets)

    def test_all_business_lines_hide_irrelevant_presets_across_staff_forms(self):
        cases = {
            "supermarket": {"cashier", "storekeeper", "branch_manager"},
            "retail": {"cashier", "storekeeper", "branch_manager"},
            "bar": {"bar_staff", "cashier", "storekeeper", "branch_manager"},
            "lounge": {"bar_staff", "cashier", "storekeeper", "branch_manager"},
            "restaurant": {"restaurant_server", "cashier", "storekeeper", "branch_manager"},
            "cafeteria": {"restaurant_server", "cashier", "storekeeper", "branch_manager"},
            "kitchen": {"storekeeper", "branch_manager"},
            "lodging": {"front_desk", "housekeeping", "storekeeper", "branch_manager"},
            "events": {"front_desk", "cashier", "branch_manager"},
            "services": {"front_desk", "cashier", "branch_manager"},
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                tenant = self.tenant_for([line])
                for cls in (StaffTeamInviteForm, StaffWorkerCreateForm, StaffMembershipManageForm, StaffMembershipBulkActionForm):
                    form = cls(tenant=tenant)
                    actual = set(dict(form.fields["role_preset"].choices)) - {""}
                    self.assertEqual(actual, expected, (line, cls.__name__))
