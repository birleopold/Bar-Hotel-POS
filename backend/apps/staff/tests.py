import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.invite_service import create_user_invite
from apps.accounts.models import Membership, MembershipRole
from apps.catalog.models import MenuCategory, MenuItem, Promotion, ServiceOffering, ServiceOfferingOption, SupermarketSkuProfile
from apps.audit.models import AuditEvent
from apps.finance.models import CashbookEntry, FinanceCategory, FinanceCategoryKind
from apps.integrations.models import IntegrationLink
from apps.inventory.models import StockBalance, StockMovement, StockReason
from apps.pos.models import (
    KdsLineStatus,
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    PaymentMethod,
    PosShift,
    PosShiftStatus,
    Refund,
    SupermarketLineReturn,
    Table,
)
from apps.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    PurchaseReceipt,
    Supplier,
)
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_KEY,
    STAFF_SESSION_SITE_KEY,
    STAFF_SESSION_TENANT_KEY,
)
from apps.staff.terminal import set_member_pin
from apps.staff.services import membership_can_manage_workspace_settings
from apps.staff.services.modules import STAFF_MODULE_KEYS, resolve_effective_staff_modules
from apps.staff.sales_summary import build_sales_summary
from apps.tenants.models import (
    Outlet,
    OutletType,
    Plan,
    Site,
    SubscriptionStatus,
    Tenant,
    TenantFeatureEntitlement,
    TenantOutletModulePolicy,
    TenantSettings,
    TenantSetupProgress,
    TenantSubscription,
)

User = get_user_model()


class SharedTerminalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Shared Terminal", slug="shared-terminal")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Counter", outlet_type=OutletType.RETAIL)
        cls.other_outlet = Outlet.objects.create(site=cls.site, name="Other", outlet_type=OutletType.RETAIL)
        cls.owner = User.objects.create_user(email="owner-terminal@test.local", password="OwnerPass9!")
        cls.worker = User.objects.create_user(email="worker-terminal@test.local", password="WorkerPass9!")
        cls.owner_member = Membership.objects.create(user=cls.owner, tenant=cls.tenant, role=MembershipRole.OWNER)
        cls.worker_member = Membership.objects.create(user=cls.worker, tenant=cls.tenant, role=MembershipRole.SERVER)
        cls.worker_member.outlets.add(cls.outlet)

    def _owner_at_counter(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        session.save()

    def test_pin_setup_requires_account_password_and_lock_switches_identity(self):
        self._owner_at_counter()
        url = reverse("staff-pin-setup")
        self.client.post(url, {"password": "bad", "pin": "276419", "confirm_pin": "276419"})
        self.owner_member.refresh_from_db()
        self.assertFalse(self.owner_member.staff_pin_hash)
        response = self.client.post(url, {"password": "OwnerPass9!", "pin": "276419", "confirm_pin": "276419"})
        self.assertEqual(response.status_code, 302)
        self.owner_member.refresh_from_db()
        self.assertNotEqual(self.owner_member.staff_pin_hash, "276419")
        set_member_pin(self.worker_member, "681347")
        locked = self.client.post(reverse("staff-terminal-lock"))
        self.assertRedirects(locked, reverse("staff-terminal"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn(STAFF_SESSION_OUTLET_KEY, self.client.session)
        page = self.client.get(reverse("staff-terminal"))
        self.assertContains(page, "Your turn to serve")
        self.assertContains(page, "worker-terminal@test.local")
        unlock = self.client.post(reverse("staff-terminal"), {"worker": str(self.worker_member.id), "pin": "681347"})
        self.assertRedirects(unlock, reverse("staff-dashboard"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.worker.id))
        self.assertEqual(self.client.session[STAFF_SESSION_OUTLET_KEY], str(self.outlet.id))
        self.assertEqual(self.client.get(reverse("staff-dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("console-org")).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/orders/").status_code, 403)
        second_tenant = Tenant.objects.create(name="Other Workspace", slug="other-terminal-workspace")
        Membership.objects.create(user=self.worker, tenant=second_tenant, role=MembershipRole.OWNER)
        self.client.post(reverse("staff-select-tenant"), {"tenant_id": str(second_tenant.id)})
        self.assertEqual(self.client.session[STAFF_SESSION_TENANT_KEY], str(self.tenant.id))

    def test_wrong_pin_locks_credential_and_full_logout_clears_terminal(self):
        self._owner_at_counter()
        set_member_pin(self.worker_member, "681347")
        self.client.post(reverse("staff-terminal-lock"))
        url = reverse("staff-terminal")
        for _ in range(5):
            self.client.post(url, {"worker": str(self.worker_member.id), "pin": "111111"})
        self.worker_member.refresh_from_db()
        self.assertIsNotNone(self.worker_member.staff_pin_locked_until)
        blocked = self.client.post(url, {"worker": str(self.worker_member.id), "pin": "681347"})
        self.assertEqual(blocked.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        # A password sign-in is always available to recover from a locked PIN.
        self.client.post(reverse("staff-login"), {"username": self.worker.email, "password": "WorkerPass9!"})
        signed_out = self.client.post(reverse("staff-logout"))
        self.assertEqual(signed_out.cookies["staff_terminal"].value, "")
        self.assertNotContains(self.client.get(url), "worker-terminal@test.local")

    def test_server_idle_timeout_ends_pin_session(self):
        self._owner_at_counter()
        set_member_pin(self.worker_member, "681347")
        self.client.post(reverse("staff-terminal-lock"))
        self.client.post(reverse("staff-terminal"), {"worker": str(self.worker_member.id), "pin": "681347"})
        session = self.client.session
        session["staff_pin_last_activity"] = 1
        session.save()
        response = self.client.get(reverse("staff-orders"))
        self.assertRedirects(response, reverse("staff-terminal"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_terminal_limits_worker_list_to_selected_outlet(self):
        self._owner_at_counter()
        self.worker_member.outlets.clear()
        self.worker_member.outlets.add(self.other_outlet)
        set_member_pin(self.worker_member, "681347")
        self.client.post(reverse("staff-terminal-lock"))
        page = self.client.get(reverse("staff-terminal"))
        self.assertNotContains(page, "worker-terminal@test.local")
        response = self.client.post(reverse("staff-terminal"), {"worker": str(self.worker_member.id), "pin": "681347"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_terminal_respects_role_outlet_types(self):
        self._owner_at_counter()
        self.worker_member.role = MembershipRole.BARTENDER
        self.worker_member.save(update_fields=["role", "updated_at"])
        set_member_pin(self.worker_member, "681347")
        self.client.post(reverse("staff-terminal-lock"))
        self.assertNotContains(self.client.get(reverse("staff-terminal")), "worker-terminal@test.local")

    def test_pin_change_invalidates_another_open_terminal_session(self):
        self._owner_at_counter()
        set_member_pin(self.worker_member, "681347")
        self.client.post(reverse("staff-terminal-lock"))
        self.client.post(reverse("staff-terminal"), {"worker": str(self.worker_member.id), "pin": "681347"})
        other = Client()
        other.force_login(self.worker)
        session = other.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        session.save()
        changed = other.post(reverse("staff-pin-setup"), {
            "password": "WorkerPass9!", "pin": "458267", "confirm_pin": "458267",
        })
        self.assertEqual(changed.status_code, 302)
        self.assertEqual(other.get(reverse("staff-dashboard")).status_code, 200)
        expired = self.client.get(reverse("staff-dashboard"))
        self.assertRedirects(expired, reverse("staff-terminal"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.post(reverse("staff-terminal"), {
            "worker": str(self.worker_member.id), "pin": "681347",
        }).status_code, 200)
        self.assertRedirects(self.client.post(reverse("staff-terminal"), {
            "worker": str(self.worker_member.id), "pin": "458267",
        }), reverse("staff-dashboard"))


class StaffUiTests(TestCase):
    def test_login_page_renders(self) -> None:
        r = self.client.get(reverse("staff-login"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Sign in")

    def test_dashboard_redirects_anonymous(self) -> None:
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/staff/login", r.url)

    def test_login_and_dashboard(self) -> None:
        User.objects.create_user(email="staff-ui@test.local", password="TestPass9!")
        r = self.client.post(
            reverse("staff-login"),
            {"username": "staff-ui@test.local", "password": "TestPass9!"},
        )
        self.assertEqual(r.status_code, 302)
        r2 = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "No workspace")

    def test_authenticated_workspace_uses_sector_aware_sidebar_shell(self) -> None:
        tenant = Tenant.objects.create(name="Multi Venue", slug="multi-venue-sidebar")
        TenantSettings.objects.get_or_create(tenant=tenant)
        site = Site.objects.create(tenant=tenant, name="Central")
        Outlet.objects.create(site=site, name="Main supermarket", outlet_type=OutletType.SUPERMARKET)
        Outlet.objects.create(site=site, name="Terrace bar", outlet_type=OutletType.BAR)
        user = User.objects.create_user(email="sidebar-owner@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        session.save()

        response = self.client.get(reverse("staff-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="staff-sidebar"')
        self.assertContains(response, "All sections")
        self.assertContains(response, "Main supermarket")
        self.assertContains(response, "Terrace bar")
        self.assertContains(response, "Sales &amp; floor")
        self.assertContains(response, "Stock &amp; buying")
        self.assertContains(response, "Workspace")

    def test_workspace_named_urls_reverse(self) -> None:
        self.assertEqual(reverse("staff-workspace-branding"), "/staff/settings/branding/")
        self.assertEqual(reverse("staff-workspace-modules"), "/staff/settings/modules/")
        self.assertEqual(reverse("staff-workspace-integrations"), "/staff/settings/integrations/")
        self.assertEqual(reverse("staff-workspace-integration-create"), "/staff/settings/integrations/new/")
        self.assertEqual(reverse("staff-workspace-efris"), "/staff/settings/integrations/efris/")
        self.assertEqual(reverse("staff-workspace-members"), "/staff/settings/members/")
        self.assertEqual(reverse("staff-workspace-member-create"), "/staff/settings/members/new/")
        self.assertEqual(reverse("staff-workspace-member-bulk-action"), "/staff/settings/members/bulk-action/")
        self.assertEqual(reverse("staff-workspace-invites"), "/staff/settings/invites/")
        self.assertEqual(reverse("staff-workspace-invite-create"), "/staff/settings/invites/new/")
        self.assertEqual(reverse("staff-promotions"), "/staff/promotions/")
        self.assertEqual(reverse("staff-lodging-folios"), "/staff/lodging/folios/")
        self.assertEqual(reverse("staff-workspace-audit"), "/staff/settings/activity/")
        self.assertEqual(reverse("staff-lodging-room-types"), "/staff/lodging/room-types/")
        self.assertEqual(reverse("staff-table-create"), "/staff/tables/new/")
        self.assertEqual(reverse("staff-promotion-create"), "/staff/promotions/new/")
        self.assertEqual(reverse("staff-finance-entries"), "/staff/finance/")
        self.assertEqual(reverse("staff-finance-entry-create"), "/staff/finance/new/")
        self.assertEqual(reverse("staff-finance-categories-new"), "/staff/finance/categories/new/")
        self.assertEqual(reverse("staff-lodging-housekeeping"), "/staff/lodging/housekeeping/")
        self.assertEqual(reverse("staff-lodging-tape"), "/staff/lodging/tape-chart/")

    def test_dashboard_owner_without_sites_shows_property_setup_cta(self) -> None:
        tenant = Tenant.objects.create(name="Empty Org", slug="empty-org-dash-cta")
        TenantSettings.objects.get_or_create(tenant=tenant)
        user = User.objects.create_user(email="empty-own-dash@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        s.save()
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Finish business setup")

    def test_dashboard_owner_site_without_outlets_shows_property_setup_cta(self) -> None:
        tenant = Tenant.objects.create(name="Site Only", slug="site-only-dash-cta")
        TenantSettings.objects.get_or_create(tenant=tenant)
        Site.objects.create(tenant=tenant, name="Solo")
        user = User.objects.create_user(email="siteonly@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        s.save()
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Finish business setup")

    def test_dashboard_owner_with_outlet_still_shows_property_setup_cta(self) -> None:
        tenant = Tenant.objects.create(name="Full Org", slug="full-org-dash-cta")
        TenantSettings.objects.get_or_create(tenant=tenant)
        site = Site.objects.create(tenant=tenant, name="S1")
        Outlet.objects.create(site=site, name="O1", outlet_type=OutletType.BAR)
        user = User.objects.create_user(email="full-own-dash@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        s.save()
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Finish business setup")

    def test_dashboard_owner_hides_property_setup_cta_when_required_steps_complete(self) -> None:
        tenant = Tenant.objects.create(name="Setup Done Org", slug="setup-done-org-dash-cta")
        TenantSettings.objects.get_or_create(tenant=tenant)
        site = Site.objects.create(tenant=tenant, name="S1")
        outlet = Outlet.objects.create(site=site, name="O1", outlet_type=OutletType.BAR)
        category = MenuCategory.objects.create(tenant=tenant, name="Food")
        item = MenuItem.objects.create(
            tenant=tenant,
            category=category,
            name="Rice",
            unit_price=Decimal("2.00"),
        )
        user = User.objects.create_user(email="setup-done-own-dash@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        StockMovement.objects.create(
            tenant=tenant,
            outlet=outlet,
            menu_item=item,
            quantity_change=Decimal("10"),
            reason=StockReason.RECEIVE,
            created_by=user,
            note="Initial receive",
        )
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        s.save()
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Finish business setup")

    def test_dashboard_server_without_sites_hides_property_setup_cta(self) -> None:
        tenant = Tenant.objects.create(name="Srv Org", slug="srv-org-dash-cta")
        TenantSettings.objects.get_or_create(tenant=tenant)
        user = User.objects.create_user(email="srv-dash@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.SERVER)
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        s.save()
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Finish business setup")
        self.assertNotContains(r, "Administration")
        self.assertNotContains(r, "Open admin console")

    def test_dashboard_owner_sees_admin_console_card(self) -> None:
        tenant = Tenant.objects.create(name="Own Org", slug="own-org-admin-card")
        TenantSettings.objects.get_or_create(tenant=tenant)
        user = User.objects.create_user(email="own-admin-card@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        s.save()
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Administration")
        self.assertContains(r, "Open admin console")
        self.assertContains(r, "Team & onboarding")
        self.assertContains(r, reverse("staff-workspace-member-create"))
        self.assertContains(r, reverse("staff-workspace-members"))

    def test_dashboard_owner_sees_setup_progress_message(self) -> None:
        tenant = Tenant.objects.create(name="Prog Org", slug="prog-org-dash-cta")
        TenantSettings.objects.get_or_create(tenant=tenant)
        user = User.objects.create_user(email="prog-own@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        s.save()
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Core setup is")

    def test_dashboard_owner_can_hide_and_resume_setup_prompt(self) -> None:
        tenant = Tenant.objects.create(name="Hide Org", slug="hide-org-dash-cta")
        TenantSettings.objects.get_or_create(tenant=tenant)
        user = User.objects.create_user(email="hide-own@test.local", password="TestPass9!")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        s.save()
        r1 = self.client.get(reverse("staff-dashboard"))
        self.assertContains(r1, "Finish business setup")
        r2 = self.client.post(reverse("staff-setup-prompt-dismiss"))
        self.assertEqual(r2.status_code, 302)
        r3 = self.client.get(reverse("staff-dashboard"))
        self.assertNotContains(r3, "Finish business setup")
        self.assertContains(r3, "Setup checklist hidden")
        prog = TenantSetupProgress.objects.get(tenant=tenant)
        self.assertTrue(prog.suppress_dashboard_prompt)
        r4 = self.client.post(reverse("staff-setup-prompt-resume"))
        self.assertEqual(r4.status_code, 302)
        self.assertEqual(r4.url, reverse("console-org-setup"))
        prog.refresh_from_db()
        self.assertFalse(prog.suppress_dashboard_prompt)


class StaffWorkspaceAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Workspace Test Org", slug="ws-test-org")
        TenantSettings.objects.get_or_create(tenant=cls.tenant)

    def _login_with_tenant(self, user) -> None:
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_owner_branding_includes_save_form(self) -> None:
        user = User.objects.create_user(email="owner-ws@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-branding"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Save workspace settings")

    def test_owner_modules_page_renders(self) -> None:
        user = User.objects.create_user(email="own-mod@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-modules"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Save staff areas")

    def test_owner_can_save_staff_modules_subset(self) -> None:
        user = User.objects.create_user(email="own-mod-save@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("staff-workspace-modules"),
            {"modules": ["pos", "workspace", "kitchen"]},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-workspace-modules"))
        ts = TenantSettings.objects.get(tenant=self.tenant)
        self.assertEqual(set(ts.enabled_staff_modules), {"pos", "workspace", "kitchen"})

    def test_accountant_modules_read_only(self) -> None:
        user = User.objects.create_user(email="acct-mod@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-modules"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Read-only for your role")
        self.assertNotContains(r, "Save staff areas")

    def test_accountant_post_modules_redirects(self) -> None:
        user = User.objects.create_user(email="acct-mod-post@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("staff-workspace-modules"),
            {"modules": ["pos"]},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-workspace-modules"))

    def test_accountant_branding_read_only_copy(self) -> None:
        user = User.objects.create_user(email="acct-ws@test.local", password="TestPass9!")
        m = Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-branding"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Read-only for your role")
        self.assertNotContains(r, "Save workspace settings")
        self.assertFalse(membership_can_manage_workspace_settings(m))

    def test_integrations_owner_sees_add_link(self) -> None:
        user = User.objects.create_user(email="own-int@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.TENANT_ADMIN,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-integrations"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "New link")

    def test_integrations_accountant_no_add_link(self) -> None:
        user = User.objects.create_user(email="acct-int@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-integrations"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Read-only list")
        self.assertNotContains(r, "New link")

    def test_integration_create_forbidden_for_accountant(self) -> None:
        user = User.objects.create_user(email="acct-new@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-integration-create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("staff-workspace-integrations"), r.url)

    def test_site_manager_cannot_post_branding(self) -> None:
        user = User.objects.create_user(email="mgr-ws@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.SITE_MANAGER,
        )
        self._login_with_tenant(user)
        ts = TenantSettings.objects.get(tenant=self.tenant)
        original_primary = ts.theme_primary
        r = self.client.post(
            reverse("staff-workspace-branding"),
            {
                "default_currency": "USD",
                "default_timezone": "UTC",
                "receipt_footer": "",
                "theme_primary": "#000000",
                "theme_secondary": "#111111",
                "theme_accent": "#222222",
                "logo_url": "",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-workspace-branding"))
        ts.refresh_from_db()
        self.assertEqual(ts.theme_primary, original_primary)

    def test_integration_create_post_owner_happy_path(self) -> None:
        user = User.objects.create_user(email="own-int-post@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        provider_key = f"test_hook_{uuid.uuid4().hex[:10]}"
        r = self.client.post(
            reverse("staff-workspace-integration-create"),
            {
                "provider_key": provider_key,
                "label": "Test integration",
                "is_enabled": "on",
                "settings_json": '{"region": "eu-west-1"}',
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, provider_key)
        link = IntegrationLink.objects.get(tenant=self.tenant, provider_key=provider_key)
        self.assertEqual(link.label, "Test integration")
        self.assertTrue(link.is_enabled)
        self.assertEqual(link.settings, {"region": "eu-west-1"})

    def test_efris_settings_owner_page_renders(self) -> None:
        user = User.objects.create_user(email="own-efris@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-efris"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "URA EFRIS setup")
        self.assertContains(r, "Run health check")
        self.assertContains(r, "Submission queue")

    @patch("apps.staff.views_workspace.get_efris_adapter")
    def test_efris_health_check_owner_uses_form_settings(self, mocked_get_adapter) -> None:
        adapter = Mock()
        adapter.health_check_settings.return_value = Mock(success=True, error_message="")
        mocked_get_adapter.return_value = adapter
        user = User.objects.create_user(email="own-efris-health@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        payload = {
            "action": "health_check",
            "tenant_efris_enabled": "on",
            "link_is_enabled": "on",
            "submit_endpoint": "https://efris.example/api/submit",
            "auth_endpoint": "",
            "tin": "1234567890",
            "branch_id": "001",
            "device_no": "DVC-1",
            "access_token": "token-1",
            "client_id": "",
            "client_secret": "",
            "api_key": "",
            "api_secret": "",
            "signing_key": "",
            "encryption_key": "",
            "signing_mode": "hmac_sha256",
            "encryption_mode": "none",
            "request_timeout_seconds": "30",
            "extra_headers_json": "{}",
        }
        r = self.client.post(reverse("staff-workspace-efris"), payload)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "EFRIS health check passed")
        adapter.health_check_settings.assert_called_once()

    def test_efris_settings_forbidden_for_accountant(self) -> None:
        user = User.objects.create_user(email="acct-efris@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-efris"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("staff-workspace-integrations"), r.url)

    def test_efris_save_can_rotate_single_secret_and_keep_others_masked(self) -> None:
        user = User.objects.create_user(email="own-efris-rotate@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        IntegrationLink.objects.create(
            tenant=self.tenant,
            provider_key="ura_efris",
            label="URA EFRIS",
            is_enabled=True,
            settings={
                "submit_endpoint": "https://efris.example/api/submit",
                "tin": "1234567890",
                "branch_id": "001",
                "device_no": "DVC-1",
                "access_token": "old-access-token",
                "client_secret": "old-client-secret",
                "api_secret": "old-api-secret",
                "signing_mode": "hmac_sha256",
                "encryption_mode": "none",
            },
        )
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("staff-workspace-efris"),
            {
                "action": "save",
                "tenant_efris_enabled": "on",
                "link_is_enabled": "on",
                "submit_endpoint": "https://efris.example/api/submit",
                "auth_endpoint": "",
                "tin": "1234567890",
                "branch_id": "001",
                "device_no": "DVC-1",
                "access_token": "new-access-token",
                "client_id": "",
                "client_secret": "****",
                "api_key": "",
                "api_secret": "****",
                "signing_key": "",
                "encryption_key": "",
                "signing_mode": "hmac_sha256",
                "encryption_mode": "none",
                "request_timeout_seconds": "30",
                "extra_headers_json": "{}",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-workspace-efris"))
        link = IntegrationLink.objects.get(tenant=self.tenant, provider_key="ura_efris")
        self.assertEqual(link.settings.get("access_token"), "new-access-token")
        self.assertEqual(link.settings.get("client_secret"), "old-client-secret")
        self.assertEqual(link.settings.get("api_secret"), "old-api-secret")

    def test_invite_create_forbidden_for_accountant(self) -> None:
        user = User.objects.create_user(email="acct-inv@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-workspace-invite-create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("staff-workspace-invites"), r.url)

    def test_promotions_list_ok_for_outlet_manager(self) -> None:
        user = User.objects.create_user(email="promo-view@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OUTLET_MANAGER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-promotions"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Offers")
        self.assertNotContains(r, "New offer")

    def test_promotions_list_forbidden_for_server(self) -> None:
        user = User.objects.create_user(email="promo-srv@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-promotions"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-dashboard"))

    def test_promotions_list_owner_sees_create(self) -> None:
        user = User.objects.create_user(email="promo-own@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-promotions"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "New promotion")

    def test_promotion_create_forbidden_for_accountant(self) -> None:
        user = User.objects.create_user(email="promo-acct@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self._login_with_tenant(user)
        r = self.client.get(reverse("staff-promotion-create"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-promotions"))

    def test_owner_can_create_percent_promotion(self) -> None:
        user = User.objects.create_user(email="promo-post@test.local", password="TestPass9!")
        Membership.objects.create(
            user=user,
            tenant=self.tenant,
            role=MembershipRole.TENANT_ADMIN,
        )
        self._login_with_tenant(user)
        r = self.client.post(
            reverse("staff-promotion-create"),
            {
                "name": "Happy hour",
                "discount_percent": "10",
                "discount_amount": "",
                "min_order_subtotal": "",
                "starts_at": "2030-06-01T16:00",
                "ends_at": "",
                "is_active": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-promotions"))
        p = Promotion.objects.get(tenant=self.tenant, name="Happy hour")
        self.assertEqual(p.discount_percent, Decimal("10"))
        self.assertIsNone(p.discount_amount)


class StaffLodgingFolioHubTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Folio Hub Tenant", slug="folio-hub-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Seaside Inn")
        cls.user = User.objects.create_user(email="folio-hub@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )

    def _login_lodging(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_SITE_KEY] = str(self.site.id)
        s.save()

    def test_folios_list_renders(self) -> None:
        self._login_lodging()
        r = self.client.get(reverse("staff-lodging-folios"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Folios")

    def test_room_types_list_renders(self) -> None:
        self._login_lodging()
        r = self.client.get(reverse("staff-lodging-room-types"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Room types")

    def test_tape_chart_renders(self) -> None:
        self._login_lodging()
        r = self.client.get(reverse("staff-lodging-tape"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Occupancy tape")


class StaffWorkspaceAuditLogTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Audit Staff Tenant", slug="audit-staff-tenant")
        TenantSettings.objects.get_or_create(tenant=cls.tenant)
        cls.user = User.objects.create_user(email="audit-staff@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.ACCOUNTANT,
        )

    def test_audit_log_renders(self) -> None:
        AuditEvent.objects.create(
            tenant=self.tenant,
            user=self.user,
            action="test.action",
            entity_type="TestEntity",
            entity_id="abc-123",
            payload={"ok": True},
        )
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()
        r = self.client.get(reverse("staff-workspace-audit"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Activity log")
        self.assertContains(r, "test.action")


class StaffTenantModulesAndRoleNavTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Modules Nav Tenant", slug="modules-nav-tenant")
        ts, _ = TenantSettings.objects.get_or_create(tenant=cls.tenant)
        ts.enabled_staff_modules = [
            "pos",
            "kitchen",
            "promotions",
            "inventory",
            "purchasing",
            "events",
            "workspace",
        ]
        ts.save(update_fields=["enabled_staff_modules"])
        Site.objects.create(tenant=cls.tenant, name="Main site")
        cls.owner = User.objects.create_user(email="mod-own@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.owner,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.bartender = User.objects.create_user(email="mod-bar@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.bartender,
            tenant=cls.tenant,
            role=MembershipRole.BARTENDER,
        )

    def _session(self, user) -> None:
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_owner_without_lodging_module_cannot_open_lodging(self) -> None:
        self._session(self.owner)
        r = self.client.get(reverse("staff-lodging-reservations"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-dashboard"))

    def test_bartender_redirected_from_promotions(self) -> None:
        self._session(self.bartender)
        r = self.client.get(reverse("staff-promotions"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-dashboard"))


class StaffControlPlaneEntitlementGatingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Entitlement Tenant", slug="entitlement-tenant")
        ts, _ = TenantSettings.objects.get_or_create(tenant=cls.tenant)
        ts.enabled_staff_modules = [
            "pos",
            "kitchen",
            "promotions",
            "inventory",
            "purchasing",
            "lodging",
            "events",
            "workspace",
        ]
        ts.save(update_fields=["enabled_staff_modules"])
        cls.plan = Plan.objects.create(
            name="POS Basic",
            code="pos-basic",
            included_modules=["pos", "workspace"],
        )
        TenantSubscription.objects.create(
            tenant=cls.tenant,
            plan=cls.plan,
            status=SubscriptionStatus.ACTIVE,
        )
        TenantFeatureEntitlement.objects.create(
            tenant=cls.tenant,
            module_key="promotions",
            is_enabled=True,
        )
        cls.owner = User.objects.create_user(email="ent-own@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.owner,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )

    def setUp(self) -> None:
        self.client.force_login(self.owner)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_plan_limits_modules_but_entitlement_can_enable_extra(self) -> None:
        r = self.client.get(reverse("staff-promotions"))
        self.assertEqual(r.status_code, 200)
        r2 = self.client.get(reverse("staff-inventory-movements"))
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2.url, reverse("staff-dashboard"))

    def test_suspended_subscription_blocks_all_staff_modules(self) -> None:
        sub = TenantSubscription.objects.get(tenant=self.tenant)
        sub.status = SubscriptionStatus.SUSPENDED
        sub.save(update_fields=["status", "updated_at"])
        r = self.client.get(reverse("staff-orders"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-dashboard"))


class StaffOutletPolicyModuleGatingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Outlet Policy Tenant", slug="outlet-policy-tenant")
        ts, _ = TenantSettings.objects.get_or_create(tenant=cls.tenant)
        ts.enabled_staff_modules = [
            "pos",
            "kitchen",
            "promotions",
            "inventory",
            "purchasing",
            "lodging",
            "events",
            "workspace",
        ]
        ts.save(update_fields=["enabled_staff_modules"])
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.bar_outlet = Outlet.objects.create(site=cls.site, name="Bar", outlet_type=OutletType.BAR)
        cls.super_outlet = Outlet.objects.create(
            site=cls.site,
            name="Market",
            outlet_type=OutletType.SUPERMARKET,
        )
        cls.plan = Plan.objects.create(
            name="All modules",
            code="all-modules-policy",
            included_modules=["pos", "kitchen", "promotions", "inventory", "purchasing", "lodging", "events", "workspace"],
        )
        TenantSubscription.objects.create(
            tenant=cls.tenant,
            plan=cls.plan,
            status=SubscriptionStatus.ACTIVE,
        )
        TenantOutletModulePolicy.objects.create(
            tenant=cls.tenant,
            outlet_type=OutletType.SUPERMARKET,
            enabled_modules=["pos", "inventory", "purchasing", "promotions", "workspace"],
            is_active=True,
        )
        cls.owner = User.objects.create_user(email="outlet-policy-owner@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.owner,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )

    def setUp(self) -> None:
        self.client.force_login(self.owner)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_supermarket_outlet_policy_blocks_kitchen(self) -> None:
        s = self.client.session
        s[STAFF_SESSION_OUTLET_KEY] = str(self.super_outlet.id)
        s.save()
        r = self.client.get(reverse("staff-kds"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-dashboard"))

    def test_bar_outlet_still_allows_kitchen(self) -> None:
        s = self.client.session
        s[STAFF_SESSION_OUTLET_KEY] = str(self.bar_outlet.id)
        s.save()
        r = self.client.get(reverse("staff-kds"))
        self.assertEqual(r.status_code, 200)


class StaffPurchasingReceiveGuardTests(TestCase):
    """Draft PO must not accept receive / receive_all (no stock movements)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="PO Guard Tenant", slug="po-guard-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main site")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Warehouse",
            outlet_type=OutletType.RETAIL,
        )
        cls.user = User.objects.create_user(email="po-guard@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.category = MenuCategory.objects.create(tenant=cls.tenant, name="Dry goods")
        cls.menu_item = MenuItem.objects.create(
            tenant=cls.tenant,
            category=cls.category,
            name="Test SKU",
            track_inventory=True,
            unit_price=Decimal("12.00"),
        )
        cls.supplier = Supplier.objects.create(tenant=cls.tenant, name="Guard supplier")
        cls.po = PurchaseOrder.objects.create(
            tenant=cls.tenant,
            supplier=cls.supplier,
            outlet=cls.outlet,
            status=PurchaseOrderStatus.DRAFT,
            created_by=cls.user,
        )
        cls.line = PurchaseOrderLine.objects.create(
            purchase_order=cls.po,
            menu_item=cls.menu_item,
            quantity_ordered=Decimal("10.000"),
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_draft_po_receive_post_shows_message_and_no_stock_movement(self) -> None:
        self.assertEqual(StockMovement.objects.filter(purchase_order=self.po).count(), 0)
        r = self.client.post(
            reverse("staff-purchasing-order-detail", kwargs={"po_id": self.po.id}),
            {
                "action": "receive",
                f"recv_{self.line.id}": "5",
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Goods can only be received while the order is sent or partially received.")
        self.line.refresh_from_db()
        self.assertEqual(self.line.quantity_received, Decimal("0"))
        self.assertEqual(StockMovement.objects.filter(purchase_order=self.po).count(), 0)

    def test_draft_po_receive_all_post_shows_message_and_no_stock_movement(self) -> None:
        self.assertEqual(StockMovement.objects.filter(purchase_order=self.po).count(), 0)
        r = self.client.post(
            reverse("staff-purchasing-order-detail", kwargs={"po_id": self.po.id}),
            {"action": "receive_all"},
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Goods can only be received while the order is sent or partially received.")
        self.line.refresh_from_db()
        self.assertEqual(self.line.quantity_received, Decimal("0"))
        self.assertEqual(StockMovement.objects.filter(purchase_order=self.po).count(), 0)

    def test_partial_receipt_records_delivery_history(self) -> None:
        self.po.status = PurchaseOrderStatus.SENT
        self.po.save(update_fields=["status", "updated_at"])
        r = self.client.post(
            reverse("staff-purchasing-order-detail", kwargs={"po_id": self.po.id}),
            {
                "action": "receive",
                "delivery_reference": "DN-1042",
                "receipt_note": "Two cartons received in good condition",
                f"recv_{self.line.id}": "4",
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        receipt = PurchaseReceipt.objects.get(purchase_order=self.po)
        self.assertEqual(receipt.delivery_reference, "DN-1042")
        self.assertEqual(receipt.received_by, self.user)
        self.assertEqual(receipt.lines.get().quantity_received, Decimal("4"))
        self.assertContains(r, "DN-1042")

    def test_supplier_payment_is_separate_from_receipt_and_visible_on_detail(self) -> None:
        self.po.status = PurchaseOrderStatus.SENT
        self.po.save(update_fields=["status", "updated_at"])
        self.line.unit_cost = Decimal("2.50")
        self.line.save(update_fields=["unit_cost", "updated_at"])
        url = reverse("staff-purchasing-order-detail", kwargs={"po_id": self.po.id})
        self.client.post(url, {"action": "receive", f"recv_{self.line.id}": "2"})
        self.assertEqual(CashbookEntry.objects.count(), 0)
        page = self.client.get(url)
        self.assertContains(page, "Supplier settlement")
        self.assertContains(page, "USD 5.00")
        response = self.client.post(url, {
            "action": "supplier_payment", "amount": "3.00", "method": "bank",
            "reference": "BANK-44", "idempotency_key": "staff-supplier-payment",
        }, follow=True)
        self.assertContains(response, "Supplier payment recorded.")
        self.assertContains(response, "BANK-44")
        self.assertEqual(CashbookEntry.objects.get().amount, Decimal("3.00"))


class StaffOrderPaymentTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Order Pay Tenant", slug="order-pay-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Downtown")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Main bar",
            outlet_type=OutletType.BAR,
        )
        cls.user = User.objects.create_user(email="order-pay@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            subtotal=Decimal("25.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("25.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_record_full_payment_closes_order(self) -> None:
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "record_payment",
                "amount": "25.00",
                "method": PaymentMethod.CASH,
            },
        )
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.order.status, OrderStatus.CLOSED)

    def test_mobile_money_is_available_as_a_pos_tender(self) -> None:
        response = self.client.get(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="mobile_money"')
        self.assertContains(response, "Mobile money")

        response = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "record_payment",
                "amount": "25.00",
                "method": PaymentMethod.MOBILE_MONEY,
            },
        )
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.method, PaymentMethod.MOBILE_MONEY)

    def test_order_detail_keeps_independent_panel_scrolling(self) -> None:
        response = self.client.get(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="staff-pos-order-main staff-pos-panel-scroll"',
        )
        self.assertContains(
            response,
            'class="staff-pos-order-side staff-pos-panel-scroll"',
        )
        self.assertNotContains(response, "staff-body--pos-page-scroll")

    def test_cannot_close_order_when_kitchen_line_not_ready(self) -> None:
        OrderLine.objects.create(
            order=self.order,
            label="Steak",
            quantity=Decimal("1"),
            unit_price=Decimal("25.00"),
            line_total=Decimal("25.00"),
            tax_amount=Decimal("0.00"),
            sort_order=0,
            kds_station="kitchen",
            kds_status=KdsLineStatus.PENDING,
        )
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "record_payment",
                "amount": "25.00",
                "method": PaymentMethod.CASH,
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "kitchen food items are still pending")
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)
        self.assertEqual(self.order.status, OrderStatus.OPEN)


class StaffOrderAddLineTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Add Line Tenant", slug="add-line-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Downtown")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Bar",
            outlet_type=OutletType.BAR,
        )
        cls.user = User.objects.create_user(email="add-line@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.cat = MenuCategory.objects.create(tenant=cls.tenant, name="Food")
        cls.menu_item = MenuItem.objects.create(
            tenant=cls.tenant,
            category=cls.cat,
            name="Soup",
            unit_price=Decimal("4.50"),
            tax_rate_percent=Decimal("0"),
        )
        cls.service = ServiceOffering.objects.create(
            tenant=cls.tenant,
            name="Steam bath",
            default_price=Decimal("15.00"),
            kds_station="service",
            is_active=True,
        )
        cls.service_option = ServiceOfferingOption.objects.create(
            service_offering=cls.service,
            name="VIP 60 min",
            price=Decimal("28.00"),
            duration_minutes=60,
            kds_station="spa",
            is_active=True,
            sort_order=1,
        )
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            subtotal=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_add_line_to_open_order(self) -> None:
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "add_line",
                "menu_item": str(self.menu_item.id),
                "quantity": "2",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.lines.filter(is_voided=False).count(), 1)
        ln = self.order.lines.first()
        assert ln is not None
        self.assertEqual(ln.quantity, Decimal("2"))
        self.assertGreater(self.order.total, Decimal("0"))

    def test_add_service_line_to_open_order(self) -> None:
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "add_service_line",
                "service_offering": str(self.service.id),
                "quantity": "1",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.lines.filter(is_voided=False).count(), 1)
        ln = self.order.lines.first()
        assert ln is not None
        self.assertEqual(ln.label, "Steam bath")
        self.assertEqual(ln.kds_station, "service")
        self.assertEqual(ln.pricing_source, "service")

    def test_add_service_line_with_package_uses_package_price_and_station(self) -> None:
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "add_service_line",
                "service_offering": str(self.service.id),
                "service_option": str(self.service_option.id),
                "quantity": "1",
            },
        )
        self.assertEqual(r.status_code, 302)
        ln = self.order.lines.order_by("-created_at").first()
        assert ln is not None
        self.assertEqual(ln.label, "Steam bath · VIP 60 min")
        self.assertEqual(ln.unit_price, Decimal("28.00"))
        self.assertEqual(ln.kds_station, "spa")

    def test_adjust_line_quantity_on_open_order(self) -> None:
        line = OrderLine.objects.create(
            order=self.order,
            menu_item=self.menu_item,
            label=self.menu_item.name,
            quantity=Decimal("1"),
            unit_price=self.menu_item.unit_price,
            line_total=Decimal("4.50"),
            tax_amount=Decimal("0.00"),
            sort_order=0,
        )
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "adjust_line_qty",
                "line_id": str(line.id),
                "quantity": "3",
            },
        )
        self.assertEqual(r.status_code, 302)
        line.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("3"))


class StaffSupermarketFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Supermarket Tenant", slug="supermarket-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Retail site")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Supermarket 1",
            outlet_type=OutletType.SUPERMARKET,
        )
        cls.user = User.objects.create_user(email="supermarket@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.cat = MenuCategory.objects.create(tenant=cls.tenant, name="Grocery")
        cls.item = MenuItem.objects.create(
            tenant=cls.tenant,
            category=cls.cat,
            name="Rice bag",
            barcode="123456",
            unit_price=Decimal("12.00"),
            track_inventory=True,
        )
        SupermarketSkuProfile.objects.create(
            menu_item=cls.item,
            tenant=cls.tenant,
            department="Dry goods",
            allow_fractional_quantity=False,
        )
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            subtotal=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()

    def test_supermarket_order_detail_shows_scan_lane(self) -> None:
        r = self.client.get(reverse("staff-order-detail", kwargs={"order_id": self.order.id}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Scan or enter PLU")
        self.assertContains(r, "scan_add_line")

    def test_supermarket_order_detail_hides_scanner_and_print_when_hardware_disabled(self) -> None:
        settings_obj, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)
        settings_obj.hardware_barcode_scanner_enabled = False
        settings_obj.hardware_receipt_printer_enabled = False
        settings_obj.save(
            update_fields=[
                "hardware_barcode_scanner_enabled",
                "hardware_receipt_printer_enabled",
                "updated_at",
            ]
        )
        r = self.client.get(reverse("staff-order-detail", kwargs={"order_id": self.order.id}))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "scan_add_line")
        self.assertNotContains(r, "staff-order-print-link")

    def test_scan_add_line_and_apply_discount(self) -> None:
        add = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "scan_add_line",
                "code": "123456",
                "quantity": "2",
            },
        )
        self.assertEqual(add.status_code, 302)
        line = self.order.lines.order_by("-created_at").first()
        assert line is not None
        self.assertEqual(line.quantity, Decimal("2"))
        disc = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "line_discount",
                "line_id": str(line.id),
                "discount_amount": "2.00",
                "discount_percent": "",
            },
        )
        self.assertEqual(disc.status_code, 302)
        line.refresh_from_db()
        self.assertEqual(line.line_discount_amount, Decimal("2.00"))
        self.assertEqual(line.line_total, Decimal("22.00"))

    def test_closed_order_allows_line_return_with_restock(self) -> None:
        line = OrderLine.objects.create(
            order=self.order,
            menu_item=self.item,
            label=self.item.name,
            quantity=Decimal("2"),
            unit_price=self.item.unit_price,
            line_total=Decimal("24.00"),
            tax_amount=Decimal("0.00"),
            sort_order=0,
        )
        self.order.subtotal = Decimal("24.00")
        self.order.total = Decimal("24.00")
        self.order.save(update_fields=["subtotal", "total", "updated_at"])
        StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.item,
            quantity=Decimal("10.000"),
        )
        pay = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {"action": "record_payment", "amount": "24.00", "method": PaymentMethod.CASH},
        )
        self.assertEqual(pay.status_code, 302)
        ret = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "line_return",
                "line_id": str(line.id),
                "quantity": "1",
                "reason": "Damaged pack",
                "restock": "on",
            },
        )
        self.assertEqual(ret.status_code, 302)
        self.assertTrue(
            SupermarketLineReturn.objects.filter(order_line=line, quantity=Decimal("1.000")).exists()
        )
        self.assertTrue(
            StockMovement.objects.filter(
                tenant=self.tenant,
                order=self.order,
                menu_item=self.item,
                reason=StockReason.SALE,
            ).exists()
        )
        self.assertTrue(
            StockMovement.objects.filter(
                tenant=self.tenant,
                menu_item=self.item,
                reason=StockReason.ADJUST_IN,
            ).exists()
        )

    def test_shift_open_and_close(self) -> None:
        open_r = self.client.post(
            reverse("staff-pos-shifts"),
            {"action": "open_shift", "opening_cash": "50.00", "note": "morning"},
        )
        self.assertEqual(open_r.status_code, 302)
        shift = PosShift.objects.get(tenant=self.tenant, outlet=self.outlet, status=PosShiftStatus.OPEN)
        close_r = self.client.post(
            reverse("staff-pos-shifts"),
            {"action": "close_shift", "shift_id": str(shift.id), "counted_cash": "50.00", "note": "closed"},
        )
        self.assertEqual(close_r.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual(shift.status, PosShiftStatus.CLOSED)


class StaffOrderApplyPromotionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Promo Order Tenant", slug="promo-order-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Downtown")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Bar",
            outlet_type=OutletType.BAR,
        )
        cls.user = User.objects.create_user(email="promo-ord@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            subtotal=Decimal("20.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("20.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )
        OrderLine.objects.create(
            order=cls.order,
            label="Meal",
            quantity=Decimal("1"),
            unit_price=Decimal("20.00"),
            line_total=Decimal("20.00"),
            tax_amount=Decimal("0.00"),
            sort_order=0,
        )
        cls.promotion = Promotion.objects.create(
            tenant=cls.tenant,
            name="Half off",
            discount_percent=Decimal("50"),
            starts_at=timezone.now() - timedelta(hours=1),
            is_active=True,
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_apply_promotion_to_open_order(self) -> None:
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "apply_promotion",
                "promotion": str(self.promotion.id),
            },
        )
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.applied_promotion_id, self.promotion.id)
        self.assertEqual(self.order.discount_amount, Decimal("10.00"))
        self.assertEqual(self.order.total, Decimal("10.00"))


class StaffOrderVoidLineTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Void Line Tenant", slug="void-line-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Downtown")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Bar",
            outlet_type=OutletType.BAR,
        )
        cls.user = User.objects.create_user(email="void-line@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            subtotal=Decimal("10.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )
        cls.line = OrderLine.objects.create(
            order=cls.order,
            label="Coffee",
            quantity=Decimal("1"),
            unit_price=Decimal("10.00"),
            line_total=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            sort_order=0,
        )
        cls.accountant = User.objects.create_user(email="void-acct@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.accountant,
            tenant=cls.tenant,
            role=MembershipRole.ACCOUNTANT,
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_void_line_on_open_order(self) -> None:
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "void_line",
                "line_id": str(self.line.id),
                "reason": "wrong item",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.line.refresh_from_db()
        self.assertTrue(self.line.is_voided)
        self.assertEqual(self.line.void_reason, "wrong item")

    def test_accountant_cannot_void_line(self) -> None:
        self.client.force_login(self.accountant)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "void_line",
                "line_id": str(self.line.id),
                "reason": "x",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.line.refresh_from_db()
        self.assertFalse(self.line.is_voided)

    def test_hold_order_sets_table_label(self) -> None:
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "hold_order",
                "hold_label": "BAR HOLD A",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.table_label, "BAR HOLD A")

    def test_void_order_shortcut_cancels_open_order(self) -> None:
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "void_order",
                "reason": "mistaken tab",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)

    def test_order_detail_uses_hold_modal_not_prompt(self) -> None:
        r = self.client.get(reverse("staff-order-detail", kwargs={"order_id": self.order.id}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "data-pos-hold-mask")
        self.assertContains(r, "data-pos-hold-input")
        self.assertContains(r, "data-pos-hold-save")
        self.assertNotContains(r, "window.prompt")


class StaffOrderRefundTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Refund Tenant", slug="refund-tenant-staff")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Downtown")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Bar",
            outlet_type=OutletType.BAR,
        )
        cls.user = User.objects.create_user(email="refund@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.server_user = User.objects.create_user(email="server-refund@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.server_user,
            tenant=cls.tenant,
            role=MembershipRole.SERVER,
        )
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            subtotal=Decimal("15.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("15.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_record_refund_on_closed_paid_order(self) -> None:
        self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "record_payment",
                "amount": "15.00",
                "method": PaymentMethod.CASH,
            },
        )
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "record_refund",
                "amount": "15.00",
                "reason": "comp",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Refund.objects.filter(order_id=self.order.id).count(), 1)

    def test_retail_screen_links_item_return_and_refund(self) -> None:
        self.outlet.outlet_type = OutletType.RETAIL
        self.outlet.save(update_fields=["outlet_type", "updated_at"])
        line = OrderLine.objects.create(
            order=self.order, label="Service item", quantity=Decimal("1"),
            unit_price=Decimal("15"), line_total=Decimal("15"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": self.order.id})
        self.client.post(url, {"action": "record_payment", "amount": "15.00", "method": PaymentMethod.CASH})
        page = self.client.get(url)
        self.assertContains(page, "Return and refund")
        self.assertContains(page, "Physical return only")
        response = self.client.post(url, {
            "action": "retail_line_refund", "line_id": str(line.id),
            "quantity": "1", "amount": "15.00", "reason": "Customer return",
        }, follow=True)
        self.assertContains(response, "Item return and customer refund recorded together")
        ret = SupermarketLineReturn.objects.get(order=self.order)
        self.assertEqual(ret.refund.amount, Decimal("15"))
        self.assertContains(response, "Customer return")

    def test_non_manager_cannot_record_refund(self) -> None:
        self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "record_payment",
                "amount": "15.00",
                "method": PaymentMethod.CASH,
            },
        )
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.client.force_login(self.server_user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {
                "action": "record_refund",
                "amount": "15.00",
                "reason": "comp",
            },
            follow=True,
        )
        self.assertEqual(Refund.objects.filter(order_id=self.order.id).count(), 0)
        self.assertContains(r, "Refunds require approval by a supervisor or manager.")


class StaffOrdersLaneTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Lane Tenant", slug="lane-tenant-staff")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Downtown")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Bar",
            outlet_type=OutletType.BAR,
        )
        cls.user = User.objects.create_user(email="lane@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.held_order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            is_paid=False,
            table_label="HOLD A1",
            subtotal=Decimal("8.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("8.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )
        cls.open_order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            is_paid=False,
            subtotal=Decimal("5.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("5.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )
        cls.closed_order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.CLOSED,
            is_paid=True,
            subtotal=Decimal("12.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("12.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_orders_page_shows_service_lanes(self) -> None:
        r = self.client.get(reverse("staff-orders"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, ">Held</h3>")
        self.assertContains(r, ">Open</h3>")
        self.assertContains(r, ">Recent</h3>")
        self.assertContains(r, "HOLD A1")

    def test_orders_page_keeps_active_and_history_scroll_regions(self) -> None:
        r = self.client.get(reverse("staff-orders"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="staff-pos-orders-lanes-scroll"')
        self.assertContains(r, 'class="staff-pos-orders-ledger"')
        self.assertNotContains(r, "staff-body--pos-page-scroll")

    def test_orders_search_filters_by_hold_label(self) -> None:
        r = self.client.get(reverse("staff-orders"), {"q": "HOLD A1"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "HOLD A1")
        self.assertNotContains(r, self.open_order.bill_reference)

    def test_orders_page_labels_manual_refresh_honestly(self) -> None:
        r = self.client.get(reverse("staff-orders"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Current view")
        self.assertContains(r, "Refresh")
        self.assertNotContains(r, "Degraded (retrying)")

    def test_quick_create_get_walkin_order_redirects_to_detail(self) -> None:
        before = Order.objects.filter(tenant=self.tenant).count()
        r = self.client.get(reverse("staff-order-quick-create"))
        self.assertEqual(r.status_code, 302)
        after = Order.objects.filter(tenant=self.tenant).count()
        self.assertEqual(after, before + 1)
        created = Order.objects.filter(tenant=self.tenant).order_by("-created_at").first()
        assert created is not None
        self.assertEqual(created.table_label, "")
        self.assertIn(str(created.id), r.url)

    def test_quick_create_new_walkin_order_redirects_to_detail(self) -> None:
        before = Order.objects.filter(tenant=self.tenant).count()
        r = self.client.post(
            reverse("staff-order-quick-create"),
            {"mode": "walkin"},
        )
        self.assertEqual(r.status_code, 302)
        after = Order.objects.filter(tenant=self.tenant).count()
        self.assertEqual(after, before + 1)
        created = Order.objects.filter(tenant=self.tenant).order_by("-created_at").first()
        assert created is not None
        self.assertEqual(created.status, OrderStatus.OPEN)
        self.assertEqual(created.table_label, "")
        self.assertIn(str(created.id), r.url)

    def test_quick_create_new_held_tab_redirects_to_detail(self) -> None:
        before = Order.objects.filter(tenant=self.tenant).count()
        r = self.client.post(
            reverse("staff-order-quick-create"),
            {"mode": "hold"},
        )
        self.assertEqual(r.status_code, 302)
        after = Order.objects.filter(tenant=self.tenant).count()
        self.assertEqual(after, before + 1)
        created = Order.objects.filter(tenant=self.tenant).order_by("-created_at").first()
        assert created is not None
        self.assertEqual(created.status, OrderStatus.OPEN)
        self.assertTrue(created.table_label.startswith("HOLD "))
        self.assertIn(str(created.id), r.url)


class StaffSupermarketLaneCardTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Supermarket Lane Tenant", slug="supermarket-lane-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Retail")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Super Outlet",
            outlet_type=OutletType.SUPERMARKET,
        )
        cls.user = User.objects.create_user(email="super-lane@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()

    def test_orders_page_shows_supermarket_lane_card_with_closed_status(self) -> None:
        r = self.client.get(reverse("staff-orders"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "orders-supermarket-lane-card")
        self.assertContains(r, "Supermarket lane")
        self.assertContains(r, 'data-shift-status="closed"')
        self.assertContains(r, reverse("staff-pos-shifts"))

    def test_supermarket_lane_card_shows_open_when_shift_exists(self) -> None:
        PosShift.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            status=PosShiftStatus.OPEN,
            opening_cash=Decimal("40.00"),
            expected_cash=Decimal("40.00"),
            opened_by=self.user,
        )
        r = self.client.get(reverse("staff-orders"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "orders-supermarket-lane-card")
        self.assertContains(r, "Supermarket lane")
        self.assertContains(r, 'data-shift-status="open"')
        self.assertContains(r, reverse("staff-pos-shifts"))


class StaffKdsRealtimeUiTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="KDS UI Tenant", slug="kds-ui-tenant")
        TenantSettings.objects.get_or_create(tenant=cls.tenant)
        cls.site = Site.objects.create(tenant=cls.tenant, name="KDS Site")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="KDS Bar",
            outlet_type=OutletType.BAR,
        )
        cls.user = User.objects.create_user(email="kds-ui@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            subtotal=Decimal("5.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("5.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )
        OrderLine.objects.create(
            order=cls.order,
            label="Soup",
            quantity=Decimal("1"),
            unit_price=Decimal("5.00"),
            line_total=Decimal("5.00"),
            tax_amount=Decimal("0.00"),
            sort_order=0,
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()

    def test_kds_page_shows_live_status_pill_and_websocket_path(self) -> None:
        r = self.client.get(reverse("staff-kds"))
        self.assertContains(r, 'data-kds-live-status')
        self.assertContains(r, "/ws/kds/")
        self.assertContains(r, "Reconnecting...")


class StaffKitchenHandoffFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Kitchen Handoff Tenant", slug="kitchen-handoff-tenant")
        TenantSettings.objects.get_or_create(tenant=cls.tenant)
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Restaurant",
            outlet_type=OutletType.RESTAURANT,
        )
        cls.kitchen_user = User.objects.create_user(email="kitchen-flow@test.local", password="TestPass9!")
        cls.server_user = User.objects.create_user(email="server-flow@test.local", password="TestPass9!")
        cls.other_server = User.objects.create_user(email="server-other@test.local", password="TestPass9!")
        cls.bartender_user = User.objects.create_user(email="bartender-flow@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.kitchen_user,
            tenant=cls.tenant,
            role=MembershipRole.KITCHEN,
        )
        Membership.objects.create(
            user=cls.server_user,
            tenant=cls.tenant,
            role=MembershipRole.SERVER,
        )
        Membership.objects.create(
            user=cls.other_server,
            tenant=cls.tenant,
            role=MembershipRole.SERVER,
        )
        Membership.objects.create(
            user=cls.bartender_user,
            tenant=cls.tenant,
            role=MembershipRole.BARTENDER,
        )
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            created_by=cls.server_user,
            status=OrderStatus.OPEN,
            subtotal=Decimal("16.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("16.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )
        cls.line = OrderLine.objects.create(
            order=cls.order,
            label="Steak",
            quantity=Decimal("1"),
            unit_price=Decimal("16.00"),
            line_total=Decimal("16.00"),
            tax_amount=Decimal("0.00"),
            sort_order=0,
            kds_status=KdsLineStatus.READY,
        )
        cls.bar_line = OrderLine.objects.create(
            order=cls.order,
            label="Mojito",
            quantity=Decimal("1"),
            unit_price=Decimal("8.00"),
            line_total=Decimal("8.00"),
            tax_amount=Decimal("0.00"),
            sort_order=1,
            kds_station="bar",
            kds_status=KdsLineStatus.PENDING,
        )

    def _login_at_outlet(self, user) -> None:
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()

    def test_kds_screen_stops_at_mark_ready_not_served(self) -> None:
        self._login_at_outlet(self.kitchen_user)
        r = self.client.get(reverse("staff-kds"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, ">Served<")
        self.assertNotContains(r, "kds_status\" value=\"served\"")

    def test_server_role_cannot_advance_kds_prep_status(self) -> None:
        self._login_at_outlet(self.server_user)
        pending_line = OrderLine.objects.create(
            order=self.order,
            label="Soup",
            quantity=Decimal("1"),
            unit_price=Decimal("5.00"),
            line_total=Decimal("5.00"),
            tax_amount=Decimal("0.00"),
            sort_order=1,
            kds_status=KdsLineStatus.PENDING,
        )
        r = self.client.post(
            reverse("staff-kds"),
            {
                "order_id": str(self.order.id),
                "line_id": str(pending_line.id),
                "kds_status": KdsLineStatus.IN_PREP,
            },
        )
        self.assertEqual(r.status_code, 302)
        pending_line.refresh_from_db()
        self.assertEqual(pending_line.kds_status, KdsLineStatus.PENDING)

    def test_kitchen_view_hides_bar_lines(self) -> None:
        self._login_at_outlet(self.kitchen_user)
        r = self.client.get(reverse("staff-kds"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Steak")
        self.assertNotContains(r, "Mojito")

    def test_bartender_view_shows_only_bar_lines(self) -> None:
        self._login_at_outlet(self.bartender_user)
        r = self.client.get(reverse("staff-kds"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Mojito")
        self.assertNotContains(r, "Steak")

    def test_bartender_can_advance_bar_prep_status(self) -> None:
        self._login_at_outlet(self.bartender_user)
        r = self.client.post(
            reverse("staff-kds"),
            {
                "order_id": str(self.order.id),
                "line_id": str(self.bar_line.id),
                "kds_status": KdsLineStatus.IN_PREP,
            },
        )
        self.assertEqual(r.status_code, 302)
        self.bar_line.refresh_from_db()
        self.assertEqual(self.bar_line.kds_status, KdsLineStatus.IN_PREP)

    def test_assigned_server_can_acknowledge_ready_handoff(self) -> None:
        self._login_at_outlet(self.server_user)
        r = self.client.get(reverse("staff-orders"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "ready for handoff")
        ack = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {"action": "ack_ready_line", "line_id": str(self.line.id)},
            follow=True,
        )
        self.assertEqual(ack.status_code, 200)
        self.assertContains(ack, "Handoff acknowledged")
        self.line.refresh_from_db()
        self.assertEqual(self.line.kds_status, KdsLineStatus.SERVED)

    def test_non_assigned_server_cannot_acknowledge_ready_handoff(self) -> None:
        self.line.kds_status = KdsLineStatus.READY
        self.line.save(update_fields=["kds_status", "updated_at"])
        self._login_at_outlet(self.other_server)
        r = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": self.order.id}),
            {"action": "ack_ready_line", "line_id": str(self.line.id)},
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "assigned server or a manager")
        self.line.refresh_from_db()
        self.assertEqual(self.line.kds_status, KdsLineStatus.READY)


@override_settings(TIME_ZONE="UTC")
class StaffSalesSectionSplitTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Section Sales Tenant", slug="section-sales-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Mixed", outlet_type=OutletType.RESTAURANT)
        cls.user = User.objects.create_user(email="section-sales@test.local", password="TestPass9!")
        Membership.objects.create(user=cls.user, tenant=cls.tenant, role=MembershipRole.OWNER)
        cls.order = Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            created_by=cls.user,
            status=OrderStatus.CLOSED,
            is_paid=True,
            subtotal=Decimal("30.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("30.00"),
            discount_amount=Decimal("0.00"),
            currency="USD",
        )
        OrderLine.objects.create(
            order=cls.order,
            label="Burger",
            quantity=Decimal("1"),
            unit_price=Decimal("20.00"),
            line_total=Decimal("20.00"),
            tax_amount=Decimal("0.00"),
            sort_order=0,
            kds_station="kitchen",
        )
        OrderLine.objects.create(
            order=cls.order,
            label="Soda",
            quantity=Decimal("1"),
            unit_price=Decimal("10.00"),
            line_total=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            sort_order=1,
            kds_station="bar",
        )
        pay_ts = timezone.now()
        Payment.objects.create(
            tenant=cls.tenant,
            order=cls.order,
            amount=Decimal("30.00"),
            method=PaymentMethod.CASH,
            idempotency_key="section-sales-pay-1",
            recorded_by=cls.user,
            created_at=pay_ts,
        )

    def test_sales_summary_splits_revenue_by_section(self) -> None:
        today = timezone.localdate()
        summary = build_sales_summary(self.tenant.id, today, today, outlet_id=self.outlet.id)
        section_rows = {row["section_key"]: row for row in summary["by_section"]}
        self.assertEqual(section_rows["kitchen"]["gross_sales"], Decimal("20.00"))
        self.assertEqual(section_rows["bar"]["gross_sales"], Decimal("10.00"))
        self.assertEqual(section_rows["service"]["gross_sales"], Decimal("0.00"))

    def test_sales_summary_csv_download(self) -> None:
        today = timezone.localdate()
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()
        r = self.client.get(
            reverse("staff-sales"),
            {"date_from": today.isoformat(), "date_to": today.isoformat(), "format": "csv"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"].split(";")[0], "text/csv")
        body = r.content.decode("utf-8")
        self.assertIn("net_sales", body)
        self.assertIn("Kitchen / food", body)


class StaffFinanceCsvExportTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Fin CSV Tenant", slug="fin-csv-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Branch")
        cls.user = User.objects.create_user(email="fin-csv@test.local", password="TestPass9!")
        Membership.objects.create(user=cls.user, tenant=cls.tenant, role=MembershipRole.OWNER)
        cls.cat = FinanceCategory.objects.create(
            tenant=cls.tenant,
            name="Utilities",
            kind=FinanceCategoryKind.EXPENSE,
        )
        cls.entry = CashbookEntry.objects.create(
            tenant=cls.tenant,
            category=cls.cat,
            site=cls.site,
            amount=Decimal("50.00"),
            transaction_date=timezone.localdate(),
            reference="INV-1",
            note="Power bill",
            created_by=cls.user,
        )

    def test_finance_entries_csv_respects_filters(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()
        d0 = self.entry.transaction_date.isoformat()
        r = self.client.get(
            reverse("staff-finance-entries"),
            {"date_from": d0, "date_to": d0, "format": "csv"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"].split(";")[0], "text/csv")
        body = r.content.decode("utf-8")
        self.assertIn("Utilities", body)
        self.assertIn("50.00", body)


class StaffInventoryCsvUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Inventory CSV Tenant", slug="inventory-csv-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Store", outlet_type=OutletType.RETAIL)
        cls.user = User.objects.create_user(email="inv-csv@test.local", password="TestPass9!")
        Membership.objects.create(user=cls.user, tenant=cls.tenant, role=MembershipRole.OWNER)
        cls.cat = MenuCategory.objects.create(tenant=cls.tenant, name="Stock")
        cls.item = MenuItem.objects.create(
            tenant=cls.tenant,
            category=cls.cat,
            name="Towel",
            sku="TWL-1",
            track_inventory=True,
            unit_price=Decimal("2.00"),
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()

    def test_upload_csv_creates_movements(self) -> None:
        payload = (
            "outlet,sku,reason,quantity,note\n"
            "Store,TWL-1,receive,10,opening stock\n"
            "Store,TWL-1,waste,2,damaged\n"
        ).encode("utf-8")
        upload = SimpleUploadedFile("stock.csv", payload, content_type="text/csv")
        r = self.client.post(
            reverse("staff-inventory-movement-upload"),
            {"csv_file": upload, "default_reason": StockReason.RECEIVE.value},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            StockMovement.objects.filter(tenant=self.tenant, menu_item=self.item, outlet=self.outlet).count(),
            2,
        )

    def test_can_create_tracked_item_inline_from_movement_page(self) -> None:
        r = self.client.post(
            reverse("staff-inventory-movement-create"),
            {
                "action": "create_tracked_item",
                "category": str(self.cat.id),
                "name": "Bath robe",
                "unit_price": "12.50",
                "sku": "ROBE-1",
                "barcode": "",
            },
        )
        self.assertEqual(r.status_code, 302)
        created = MenuItem.objects.filter(tenant=self.tenant, name="Bath robe").first()
        self.assertIsNotNone(created)
        assert created is not None
        self.assertTrue(created.track_inventory)
        self.assertTrue(created.is_active)

    def test_upload_template_csv_downloads(self) -> None:
        r = self.client.get(reverse("staff-inventory-movement-upload-template"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "text/csv")
        self.assertIn("stock-movement-template.csv", r["Content-Disposition"])
        self.assertIn("outlet,outlet_id,menu_item", r.content.decode("utf-8"))

    def test_upload_error_report_csv_downloads_after_failed_rows(self) -> None:
        payload = (
            "outlet,sku,reason,quantity,note\n"
            "Store,UNKNOWN,receive,10,bad sku\n"
        ).encode("utf-8")
        upload = SimpleUploadedFile("stock.csv", payload, content_type="text/csv")
        r = self.client.post(
            reverse("staff-inventory-movement-upload"),
            {"csv_file": upload},
        )
        self.assertEqual(r.status_code, 200)
        err = self.client.get(reverse("staff-inventory-movement-upload-errors"))
        self.assertEqual(err.status_code, 200)
        self.assertEqual(err["Content-Type"], "text/csv")
        self.assertIn("stock-movement-upload-errors.csv", err["Content-Disposition"])
        self.assertIn("item not found", err.content.decode("utf-8"))

    def test_ledger_shows_download_last_error_report_button_after_failed_upload(self) -> None:
        payload = (
            "outlet,sku,reason,quantity,note\n"
            "Store,UNKNOWN,receive,10,bad sku\n"
        ).encode("utf-8")
        upload = SimpleUploadedFile("stock.csv", payload, content_type="text/csv")
        self.client.post(
            reverse("staff-inventory-movement-upload"),
            {"csv_file": upload},
        )
        ledger = self.client.get(reverse("staff-inventory-movements"))
        self.assertEqual(ledger.status_code, 200)
        self.assertContains(ledger, "Download last error report")


class StaffWorkspaceMembersTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Members UI Tenant", slug="members-ui-tenant")
        TenantSettings.objects.get_or_create(tenant=cls.tenant)
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main branch")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Bar counter",
            outlet_type=OutletType.BAR,
        )
        cls.user = User.objects.create_user(email="member-list@test.local", password="TestPass9!")
        cls.membership = Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.worker_user = User.objects.create_user(email="worker@test.local", password="TestPass9!")
        cls.worker_membership = Membership.objects.create(
            user=cls.worker_user,
            tenant=cls.tenant,
            role=MembershipRole.SERVER,
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s.save()

    def test_members_list_renders(self) -> None:
        r = self.client.get(reverse("staff-workspace-members"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "member-list@test.local")
        self.assertContains(r, "Edit")

    def test_owner_can_update_worker_role_and_scope(self) -> None:
        r = self.client.post(
            reverse("staff-workspace-member-edit", kwargs={"membership_id": self.worker_membership.id}),
            {
                "role_preset": "bar_staff",
                "role": MembershipRole.BARTENDER,
                "is_active": "on",
                "sites": [str(self.site.id)],
                "outlets": [str(self.outlet.id)],
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-workspace-members"))
        self.worker_membership.refresh_from_db()
        self.assertEqual(self.worker_membership.role, MembershipRole.BARTENDER)
        self.assertEqual(list(self.worker_membership.sites.values_list("id", flat=True)), [self.site.id])
        self.assertEqual(list(self.worker_membership.outlets.values_list("id", flat=True)), [self.outlet.id])

    def test_owner_can_deactivate_worker(self) -> None:
        r = self.client.post(
            reverse("staff-workspace-member-deactivate", kwargs={"membership_id": self.worker_membership.id}),
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-workspace-members"))
        self.worker_membership.refresh_from_db()
        self.assertFalse(self.worker_membership.is_active)

    def test_owner_cannot_deactivate_self(self) -> None:
        r = self.client.post(
            reverse("staff-workspace-member-deactivate", kwargs={"membership_id": self.membership.id}),
            follow=True,
        )
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.is_active)
        self.assertContains(r, "You cannot deactivate your own workspace access.")

    def test_owner_can_create_worker_directly(self) -> None:
        r = self.client.post(
            reverse("staff-workspace-member-create"),
            {
                "first_name": "Jane",
                "last_name": "Cashier",
                "email": "new-worker@test.local",
                "phone": "555100",
                "role_preset": "cashier",
                "role": MembershipRole.SERVER,
                "sites": [str(self.site.id)],
                "outlets": [str(self.outlet.id)],
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        created = Membership.objects.get(tenant=self.tenant, user__email="new-worker@test.local")
        self.assertEqual(created.role, MembershipRole.SERVER)
        self.assertContains(r, "Password setup link ready")

    def test_owner_can_bulk_deactivate_workers(self) -> None:
        extra_user = User.objects.create_user(email="extra-worker@test.local", password="TestPass9!")
        extra_membership = Membership.objects.create(
            user=extra_user,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        r = self.client.post(
            reverse("staff-workspace-member-bulk-action"),
            {
                "member_ids": [str(self.worker_membership.id), str(extra_membership.id)],
                "action": "deactivate",
                "role_preset": "",
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.worker_membership.refresh_from_db()
        extra_membership.refresh_from_db()
        self.assertFalse(self.worker_membership.is_active)
        self.assertFalse(extra_membership.is_active)

    def test_owner_can_bulk_apply_role_preset(self) -> None:
        r = self.client.post(
            reverse("staff-workspace-member-bulk-action"),
            {
                "member_ids": [str(self.worker_membership.id)],
                "action": "apply_preset",
                "role_preset": "bar_staff",
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.worker_membership.refresh_from_db()
        self.assertEqual(self.worker_membership.role, MembershipRole.BARTENDER)

    def test_owner_can_regenerate_invite_token(self) -> None:
        inv, _ = create_user_invite(
            tenant=self.tenant,
            email="regen@test.local",
            role=MembershipRole.SERVER,
            expires_days=7,
            invited_by=self.user,
        )
        r = self.client.post(
            reverse("staff-workspace-invite-regenerate", kwargs={"invite_id": inv.id}),
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "A fresh invite token is ready below.")
        self.assertContains(r, "Copy this token now")


class StaffTableStaffTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Table Staff Tenant", slug="table-staff-tenant")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Restaurant",
            outlet_type=OutletType.RESTAURANT,
        )
        cls.owner = User.objects.create_user(email="tbl-owner@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.owner,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.accountant = User.objects.create_user(email="tbl-acct@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.accountant,
            tenant=cls.tenant,
            role=MembershipRole.ACCOUNTANT,
        )

    def _session_tenant_outlet(self, user) -> None:
        self.client.force_login(user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()

    def test_owner_can_create_table(self) -> None:
        self._session_tenant_outlet(self.owner)
        r = self.client.post(
            reverse("staff-table-create"),
            {
                "label": "Patio 1",
                "capacity": 4,
                "sort_order": 10,
                "is_active": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-tables"))
        t = Table.objects.get(outlet=self.outlet, label="Patio 1")
        self.assertEqual(t.capacity, 4)
        self.assertTrue(t.is_active)

    def test_accountant_cannot_open_table_create(self) -> None:
        self._session_tenant_outlet(self.accountant)
        r = self.client.get(reverse("staff-table-create"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("staff-tables"))


class StaffModuleResolutionFallbackTests(TestCase):
    """Guards against empty effective module sets that hide all POS / Sales / nav UI."""

    def test_disjoint_saved_modules_and_plan_modules_still_yield_operational_modules(self) -> None:
        tenant = Tenant.objects.create(name="Disjoint Mods", slug="disjoint-mods")
        ts, _ = TenantSettings.objects.get_or_create(tenant=tenant)
        ts.enabled_staff_modules = ["pos", "kitchen"]
        ts.save(update_fields=["enabled_staff_modules"])
        plan = Plan.objects.create(
            name="Lodging plan",
            code="lodging-only",
            included_modules=["lodging", "workspace"],
        )
        TenantSubscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
        )
        effective = resolve_effective_staff_modules(tenant)
        self.assertTrue(effective)
        self.assertIn("pos", effective)

    def test_outlet_policy_that_would_zero_modules_is_ignored(self) -> None:
        tenant = Tenant.objects.create(name="Policy Zero", slug="policy-zero")
        ts, _ = TenantSettings.objects.get_or_create(tenant=tenant)
        ts.enabled_staff_modules = ["pos"]
        ts.save(update_fields=["enabled_staff_modules"])
        site = Site.objects.create(tenant=tenant, name="S1")
        outlet = Outlet.objects.create(site=site, name="Bar", outlet_type=OutletType.BAR)
        plan = Plan.objects.create(
            name="Full",
            code="full",
            included_modules=list(STAFF_MODULE_KEYS),
        )
        TenantSubscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
        )
        TenantOutletModulePolicy.objects.create(
            tenant=tenant,
            outlet_type=OutletType.BAR,
            enabled_modules=["inventory"],
            is_active=True,
        )
        effective = resolve_effective_staff_modules(tenant, outlet=outlet)
        self.assertTrue(effective)
        self.assertIn("pos", effective)


class StaffDashboardLowStockInsightTests(TestCase):
    """Dashboard shows at-reorder snapshot (SYSTEMS IMS-style low stock strip)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Dash Low Stock Tenant", slug="dash-low-stock")
        ts, _ = TenantSettings.objects.get_or_create(tenant=cls.tenant)
        ts.enabled_staff_modules = ["pos", "inventory", "workspace"]
        ts.save(update_fields=["enabled_staff_modules"])
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Bar", outlet_type=OutletType.BAR)
        cls.user = User.objects.create_user(email="dash-low-stock@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )
        cls.category = MenuCategory.objects.create(tenant=cls.tenant, name="Bev")
        cls.menu_item = MenuItem.objects.create(
            tenant=cls.tenant,
            category=cls.category,
            name="Reorder Me Ale",
            track_inventory=True,
            reorder_level=Decimal("10"),
            unit_price=Decimal("5.00"),
        )
        StockBalance.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            menu_item=cls.menu_item,
            quantity=Decimal("2"),
        )
        Order.objects.create(
            tenant=cls.tenant,
            outlet=cls.outlet,
            status=OrderStatus.OPEN,
            is_paid=False,
            currency="UGX",
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()

    def test_dashboard_lists_low_stock_and_link_to_balances(self) -> None:
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Low stock")
        self.assertContains(r, "Reorder Me Ale")
        self.assertContains(r, "low_stock=1")

    def test_dashboard_shows_scoped_cross_module_workload(self) -> None:
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Operations pulse")
        self.assertContains(r, "Open orders")
        self.assertContains(r, "Awaiting settlement")
        snapshot = r.context["staff_dashboard_operations_snapshot"]
        self.assertEqual(snapshot[0].value, 1)


class StaffDashboardSalesSnapshotTests(TestCase):
    """Home shows cached sales snapshot (same window as Sales summary defaults)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = Tenant.objects.create(name="Dash Sales Tenant", slug="dash-sales")
        ts, _ = TenantSettings.objects.get_or_create(tenant=cls.tenant)
        ts.enabled_staff_modules = ["pos", "workspace"]
        ts.save(update_fields=["enabled_staff_modules"])
        cls.site = Site.objects.create(tenant=cls.tenant, name="Site")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Bar", outlet_type=OutletType.BAR)
        cls.user = User.objects.create_user(email="dash-sales@test.local", password="TestPass9!")
        Membership.objects.create(
            user=cls.user,
            tenant=cls.tenant,
            role=MembershipRole.OWNER,
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)
        s = self.client.session
        s[STAFF_SESSION_TENANT_KEY] = str(self.tenant.id)
        s[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.id)
        s.save()

    def test_dashboard_shows_sales_snapshot_and_report_link(self) -> None:
        r = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Sales snapshot")
        self.assertContains(r, "Full report")
        self.assertContains(r, reverse("staff-sales"))
        self.assertContains(r, "date_from=")
        self.assertContains(r, "date_to=")
