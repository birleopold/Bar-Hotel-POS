from django.test import TestCase

from apps.accounts.models import Membership, MembershipRole, User
from apps.customers.models import Customer
from apps.staff.services.customers import visible_customers
from apps.tenants.models import Site, Tenant


class CustomerDirectoryScopeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Privacy Tenant", slug="privacy-scope")
        self.site = Site.objects.create(tenant=self.tenant, name="Assigned site")
        self.worker = User.objects.create_user(email="privacy-worker@test.invalid", password="LongPass9!")
        self.membership = Membership.objects.create(
            tenant=self.tenant, user=self.worker, role=MembershipRole.FRONT_DESK
        )
        self.membership.sites.add(self.site)
        self.unlinked = Customer.objects.create(
            tenant=self.tenant, name="No current site", created_by=self.worker
        )

    def test_creator_does_not_bypass_current_site_scope(self):
        self.assertFalse(
            visible_customers(self.membership, self.worker).filter(pk=self.unlinked.pk).exists()
        )

    def test_inactive_membership_cannot_read_directory(self):
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])
        self.assertFalse(visible_customers(self.membership, self.worker).exists())

    def test_non_customer_role_cannot_read_directory(self):
        self.membership.role = MembershipRole.SERVER
        self.membership.save(update_fields=["role"])
        self.assertFalse(visible_customers(self.membership, self.worker).exists())
