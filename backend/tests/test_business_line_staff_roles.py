from django.test import SimpleTestCase

from apps.accounts.models import MembershipRole
from apps.accounts.role_policy import permitted_roles
from apps.staff.forms import StaffTeamInviteForm, StaffWorkerCreateForm


class FakeSettings:
    def __init__(self, lines):
        self.business_lines = lines


class FakeTenant:
    def __init__(self, lines):
        self.settings = FakeSettings(lines)


class BusinessRolePolicyTests(SimpleTestCase):
    def test_supermarket_excludes_hospitality_roles(self):
        allowed = permitted_roles(FakeTenant(["supermarket"]))
        self.assertIn(MembershipRole.SERVER, allowed)
        self.assertIn(MembershipRole.STOREKEEPER, allowed)
        for role in (MembershipRole.BARTENDER, MembershipRole.KITCHEN, MembershipRole.CLEANER, MembershipRole.FRONT_DESK):
            self.assertNotIn(role, allowed)

    def test_hotel_roles_are_relevant(self):
        allowed = permitted_roles(FakeTenant(["lodging"]))
        self.assertIn(MembershipRole.FRONT_DESK, allowed)
        self.assertIn(MembershipRole.CLEANER, allowed)
        self.assertNotIn(MembershipRole.BARTENDER, allowed)

    def test_mixed_businesses_have_union_of_roles(self):
        allowed = permitted_roles(FakeTenant(["supermarket", "bar"]))
        self.assertIn(MembershipRole.BARTENDER, allowed)
        self.assertIn(MembershipRole.STOREKEEPER, allowed)

    def test_tenant_forms_hide_irrelevant_roles_and_presets(self):
        tenant = FakeTenant(["supermarket"])
        for form_class in (StaffTeamInviteForm, StaffWorkerCreateForm):
            form = form_class(tenant=tenant)
            roles = dict(form.fields["role"].choices)
            presets = dict(form.fields["role_preset"].choices)
            self.assertNotIn(MembershipRole.BARTENDER, roles)
            self.assertNotIn("bar_staff", presets)
            self.assertIn(MembershipRole.SERVER, roles)
            self.assertIn("cashier", presets)
