from django.test import TestCase

from apps.accounts.models import Membership, MembershipRole, User
from apps.staff.services.membership import (
    sites_visible_for_membership,
    staff_accessible_outlets,
)
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class AssignedOutletSiteScopeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Outlet scope", slug="outlet-scope-check")
        self.main = Site.objects.create(tenant=self.tenant, name="Main")
        self.other = Site.objects.create(tenant=self.tenant, name="Private")
        self.counter = Outlet.objects.create(
            site=self.main, name="Counter", outlet_type=OutletType.BAR
        )
        self.private_counter = Outlet.objects.create(
            site=self.other, name="Other", outlet_type=OutletType.BAR
        )
        self.user = User.objects.create_user(
            email="outlet-scope@test.invalid", password="LongPass9!"
        )
        self.membership = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.SERVER
        )

    def test_assigned_outlet_grants_only_its_own_branch(self):
        self.membership.outlets.add(self.counter)
        self.assertEqual(
            {s.pk for s in sites_visible_for_membership(self.membership)},
            {self.main.pk},
        )
        self.assertEqual(
            {o.pk for o in staff_accessible_outlets(self.membership)},
            {self.counter.pk},
        )

    def test_unassigned_server_sees_no_branches_or_outlets(self):
        self.assertEqual(sites_visible_for_membership(self.membership), [])
        self.assertEqual(staff_accessible_outlets(self.membership), [])

    def test_explicit_site_scope_stays_authoritative(self):
        self.membership.sites.add(self.main)
        self.membership.outlets.add(self.private_counter)
        self.assertEqual(
            {s.pk for s in sites_visible_for_membership(self.membership)},
            {self.main.pk},
        )
        self.assertEqual(staff_accessible_outlets(self.membership), [])
