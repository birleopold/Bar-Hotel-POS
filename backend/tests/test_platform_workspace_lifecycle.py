"""Regression coverage for platform workspace onboarding and control-plane flows.

These paths previously returned 500 with production PostgreSQL RLS enabled.
SQLite exercises view behavior; production RLS must also be checked with the
non-owner PostgreSQL application role before release certification.
"""
from datetime import timedelta

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
    def test_platform_pages_stay_neutral_when_tenant_session_is_stale(self):
        from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
        tenant = Tenant.objects.create(name="Fizo Test Tenant", slug="fizo-neutrality")
        TenantSettings.objects.create(tenant=tenant, business_lines=["supermarket"])
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(tenant.pk)
        session.save()

        response = self.client.get(reverse("console-platform-tenants"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["console_active_tenant"])
        self.assertFalse(response.context["grocery_console_shell"])
        self.assertFalse(response.context["hospitality_console_shell"])

    def test_platform_shell_uses_fresh_neutral_navigation_contract(self):
        tenant = Tenant.objects.create(name="Tenant that must stay hidden", slug="hidden-platform-tenant")
        TenantSettings.objects.create(tenant=tenant, business_lines=["supermarket"])
        session = self.client.session
        from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
        session[STAFF_SESSION_TENANT_KEY] = str(tenant.pk)
        session.save()

        response = self.client.get(reverse("console-platform-tenants"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="fz-brand"')
        self.assertContains(response, 'class="fz-nav"')
        self.assertContains(response, 'class="fz-top-title"')
        self.assertContains(response, "Platform administration")
        self.assertContains(response, "Workspaces")
        self.assertContains(response, "Plans")
        self.assertContains(response, "fizo-fresh.css")
        self.assertContains(response, "v=20261028.1")
        self.assertNotContains(response, 'id="console-tenant-select"')
        self.assertNotContains(response, "Tenant that must stay hidden")
        self.assertNotContains(response, 'class="wb-side-nav"')
        self.assertNotContains(response, 'class="staff-sidebar__brand"')

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="platform-operator@example.test", password="test-password-safe"
        )
        self.client.force_login(self.user)

    def test_platform_pages_share_one_fresh_component_system(self):
        tenant = Tenant.objects.create(name="Shell tenant", slug="shell-tenant")
        TenantSettings.objects.create(tenant=tenant)

        workspace_list = self.client.get(reverse("console-platform-tenants"))
        self.assertEqual(workspace_list.status_code, 200)
        self.assertContains(workspace_list, 'class="platform-page"')
        self.assertContains(workspace_list, 'class="platform-overview"')
        self.assertNotContains(workspace_list, "<style>")

        plan_list = self.client.get(reverse("console-platform-plans"))
        self.assertEqual(plan_list.status_code, 200)
        self.assertContains(plan_list, "Plans &amp; modules")
        self.assertContains(plan_list, 'class="platform-page"')

        create_workspace = self.client.get(reverse("console-platform-tenant-create"))
        self.assertEqual(create_workspace.status_code, 200)
        self.assertContains(create_workspace, 'class="staff-card platform-form"')

        control = self.client.get(
            reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        )
        self.assertEqual(control.status_code, 200)
        self.assertContains(control, 'class="platform-control"')
        self.assertContains(control, 'class="platform-control__grid"')
        self.assertContains(control, "Back to workspaces")

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

    def test_training_status_is_chosen_at_creation_and_immutable_on_edit(self):
        create_url = reverse("console-platform-tenant-create")
        response = self.client.post(
            create_url,
            {
                "name": "Training Store",
                "slug": "training-store-platform",
                "is_active": "on",
                "is_training": "on",
            },
        )
        self.assertRedirects(response, reverse("console-platform-tenants"))
        tenant = Tenant.objects.get(slug="training-store-platform")
        self.assertTrue(tenant.is_training)

        edit_url = reverse(
            "console-platform-tenant-edit",
            kwargs={"tenant_id": tenant.pk},
        )
        page = self.client.get(edit_url)
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["form"].fields["is_training"].disabled)

        # Even a crafted edit POST cannot convert training to live.
        response = self.client.post(
            edit_url,
            {
                "name": "Training Store Renamed",
                "slug": tenant.slug,
                "is_active": "on",
                "is_training": "",
            },
        )
        self.assertRedirects(response, reverse("console-platform-tenants"))
        tenant.refresh_from_db()
        self.assertTrue(tenant.is_training)
        self.assertEqual(tenant.name, "Training Store Renamed")

    def test_workspace_pause_requires_reason_and_preserves_state_when_missing(self):
        tenant = Tenant.objects.create(name="Pause reason", slug="pause-reason")
        TenantSettings.objects.create(tenant=tenant)
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})

        response = self.client.post(url, {"toggle_tenant_access": "1"})
        self.assertRedirects(response, url)
        tenant.refresh_from_db()
        self.assertTrue(tenant.is_active)

        response = self.client.post(url, {
            "toggle_tenant_access": "1",
            "access_reason": "Customer requested temporary suspension",
        })
        self.assertRedirects(response, url)
        tenant.refresh_from_db()
        self.assertFalse(tenant.is_active)

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

    def test_supermarket_preset_refuses_mixed_tenant_without_reconfiguring(self):
        from apps.tenants.models import Plan, TenantSubscription, SubscriptionStatus
        tenant = Tenant.objects.create(name="Mixed business", slug="mixed-business-preset")
        TenantSettings.objects.create(
            tenant=tenant, business_lines=["supermarket", "restaurant"],
        )
        plan = Plan.objects.create(code="mixed-custom-plan", name="Mixed Plan", monthly_price=120)
        TenantSubscription.objects.create(
            tenant=tenant, plan=plan, status=SubscriptionStatus.TRIAL,
        )
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        response = self.client.post(url, {"provision_supermarket": "1"})
        self.assertRedirects(response, url)
        sub = TenantSubscription.objects.get(tenant=tenant)
        self.assertEqual(sub.plan_id, plan.pk)
        self.assertEqual(sub.status, SubscriptionStatus.TRIAL)
        self.assertEqual(
            TenantSettings.objects.get(tenant=tenant).business_lines,
            ["supermarket", "restaurant"],
        )

    def test_supermarket_preset_provisions_fresh_tenant(self):
        from apps.tenants.models import TenantSubscription, Outlet, OutletType
        tenant = Tenant.objects.create(name="Fresh store", slug="fresh-store-preset")
        TenantSettings.objects.create(tenant=tenant, business_lines=["supermarket"])
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        response = self.client.post(url, {"provision_supermarket": "1"})
        self.assertRedirects(response, url)
        self.assertEqual(
            TenantSubscription.objects.get(tenant=tenant).plan.code,
            "supermarket-core",
        )
        self.assertTrue(Outlet.objects.filter(
            site__tenant=tenant, outlet_type=OutletType.SUPERMARKET,
        ).exists())

    def test_subscription_transition_requires_reason_and_clears_cancelled_date_on_reactivation(self):
        from apps.tenants.models import (
            Plan, TenantSubscription, SubscriptionStatus, BillingEvent,
            BillingEventType,
        )
        tenant = Tenant.objects.create(name="Subscription control", slug="subscription-control")
        TenantSettings.objects.create(tenant=tenant)
        plan = Plan.objects.create(name="Lifecycle Plan", code="lifecycle-test")
        subscription = TenantSubscription.objects.create(
            tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE,
        )
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        denied = self.client.post(url, {
            "transition_subscription": "1",
            "trn-target_status": SubscriptionStatus.SUSPENDED,
            "trn-reason": "",
        })
        self.assertEqual(denied.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertContains(denied, "Give a reason for suspension or cancellation.")

        for target, reason in [
            (SubscriptionStatus.CANCELLED, "Customer requested closure"),
            (SubscriptionStatus.ACTIVE, "Reactivated on customer request"),
        ]:
            response = self.client.post(url, {
                "transition_subscription": "1",
                "trn-target_status": target,
                "trn-reason": reason,
            })
            self.assertRedirects(response, url)
            subscription.refresh_from_db()
            self.assertEqual(subscription.status, target)
            self.assertEqual(subscription.cancelled_at is not None, target == SubscriptionStatus.CANCELLED)

        count = BillingEvent.objects.filter(
            tenant=tenant, event_type=BillingEventType.SUBSCRIPTION_STATUS_CHANGED,
        ).count()
        response = self.client.post(url, {
            "transition_subscription": "1",
            "trn-target_status": SubscriptionStatus.ACTIVE,
            "trn-reason": "Repeated click",
        })
        self.assertRedirects(response, url)
        self.assertEqual(BillingEvent.objects.filter(
            tenant=tenant, event_type=BillingEventType.SUBSCRIPTION_STATUS_CHANGED,
        ).count(), count)

    def test_paying_last_past_due_invoice_reactivates_only_past_due_subscription(self):
        from apps.tenants.models import (
            BillingEvent, BillingEventType, BillingInvoice, BillingInvoiceStatus,
            Plan, SubscriptionStatus, TenantSubscription,
        )
        tenant = Tenant.objects.create(name="Billing reconcile", slug="billing-reconcile")
        TenantSettings.objects.create(tenant=tenant)
        plan = Plan.objects.create(name="Billing Reconcile Plan", code="billing-reconcile-plan")
        subscription = TenantSubscription.objects.create(
            tenant=tenant, plan=plan, status=SubscriptionStatus.PAST_DUE,
        )
        invoice = BillingInvoice.objects.create(
            tenant=tenant,
            subscription=subscription,
            invoice_number="INV-RECON-1",
            amount="100.00",
            currency="UGX",
            status=BillingInvoiceStatus.PAST_DUE,
        )
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        response = self.client.post(url, {
            "invoice_set_status": "1",
            "invoice_id": str(invoice.pk),
            "status": BillingInvoiceStatus.PAID,
        })
        self.assertRedirects(response, url)
        subscription.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertIsNotNone(invoice.paid_at)
        self.assertTrue(BillingEvent.objects.filter(
            tenant=tenant,
            event_type=BillingEventType.SUBSCRIPTION_STATUS_CHANGED,
            previous_subscription_status=SubscriptionStatus.PAST_DUE,
            new_subscription_status=SubscriptionStatus.ACTIVE,
        ).exists())

        subscription.status = SubscriptionStatus.SUSPENDED
        subscription.save(update_fields=["status", "updated_at"])
        second = BillingInvoice.objects.create(
            tenant=tenant,
            subscription=subscription,
            invoice_number="INV-RECON-2",
            amount="200.00",
            currency="UGX",
            status=BillingInvoiceStatus.PAST_DUE,
        )
        response = self.client.post(url, {
            "invoice_set_status": "1",
            "invoice_id": str(second.pk),
            "status": BillingInvoiceStatus.PAID,
        })
        self.assertRedirects(response, url)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.SUSPENDED)

    def test_subscription_and_invoice_forms_reject_impossible_dates_and_amounts(self):
        from django.utils import timezone
        from apps.console.forms import ConsoleBillingInvoiceForm, ConsoleTenantSubscriptionForm
        from apps.tenants.models import BillingInvoiceStatus, Plan, SubscriptionStatus
        plan = Plan.objects.create(name="Validation Plan", code="validation-plan")
        now = timezone.now()
        subscription_form = ConsoleTenantSubscriptionForm(data={
            "plan": str(plan.pk),
            "status": SubscriptionStatus.ACTIVE,
            "started_at": now.strftime("%Y-%m-%dT%H:%M"),
            "trial_ends_at": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "current_period_ends_at": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "cancelled_at": "",
        })
        self.assertFalse(subscription_form.is_valid())
        self.assertIn("trial_ends_at", subscription_form.errors)
        self.assertIn("current_period_ends_at", subscription_form.errors)

        invoice_form = ConsoleBillingInvoiceForm(data={
            "invoice_number": "INV-BAD-DATES",
            "amount": "-1.00",
            "currency": "ugx",
            "status": BillingInvoiceStatus.ISSUED,
            "issued_at": now.strftime("%Y-%m-%dT%H:%M"),
            "due_at": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "paid_at": now.strftime("%Y-%m-%dT%H:%M"),
            "external_ref": "",
            "note": "",
        })
        self.assertFalse(invoice_form.is_valid())
        self.assertIn("amount", invoice_form.errors)
        self.assertIn("due_at", invoice_form.errors)

    def test_existing_subscription_status_cannot_bypass_audited_transition_form(self):
        from apps.tenants.models import Plan, SubscriptionStatus, TenantSubscription
        tenant = Tenant.objects.create(name="Audited status", slug="audited-status")
        TenantSettings.objects.create(tenant=tenant)
        first_plan = Plan.objects.create(name="Audited Plan A", code="audited-plan-a")
        second_plan = Plan.objects.create(name="Audited Plan B", code="audited-plan-b")
        subscription = TenantSubscription.objects.create(
            tenant=tenant, plan=first_plan, status=SubscriptionStatus.ACTIVE,
        )
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        response = self.client.post(url, {
            "save_subscription": "1",
            "sub-plan": str(second_plan.pk),
            "sub-status": SubscriptionStatus.SUSPENDED,
            "sub-started_at": "",
            "sub-trial_ends_at": "",
            "sub-current_period_ends_at": "",
            "sub-cancelled_at": "",
        })
        self.assertRedirects(response, url)
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, second_plan.pk)
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)

    def test_platform_workspace_list_counts_blocked_access_and_filters_expired_trials(self):
        from django.utils import timezone
        from apps.tenants.models import Plan, SubscriptionStatus, TenantSubscription
        plan = Plan.objects.create(name="List Access Plan", code="list-access-plan")
        active = Tenant.objects.create(name="Access Active", slug="access-active")
        expired = Tenant.objects.create(name="Access Expired", slug="access-expired")
        suspended = Tenant.objects.create(name="Access Suspended", slug="access-suspended")
        for tenant in (active, expired, suspended):
            TenantSettings.objects.create(tenant=tenant)
        TenantSubscription.objects.create(
            tenant=active, plan=plan, status=SubscriptionStatus.ACTIVE,
        )
        TenantSubscription.objects.create(
            tenant=expired,
            plan=plan,
            status=SubscriptionStatus.TRIAL,
            trial_ends_at=timezone.now() - timedelta(hours=1),
        )
        TenantSubscription.objects.create(
            tenant=suspended, plan=plan, status=SubscriptionStatus.SUSPENDED,
        )

        url = reverse("console-platform-tenants")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tenant_total"], 3)
        self.assertEqual(response.context["tenant_active"], 1)
        self.assertEqual(response.context["tenant_needs_attention"], 2)
        self.assertContains(response, "Access Expired")
        self.assertContains(response, "Blocked")

        filtered = self.client.get(url, {"subscription": "expired_trial"})
        self.assertEqual(filtered.status_code, 200)
        self.assertContains(filtered, "Access Expired")
        self.assertEqual(
            [tenant.name for tenant in filtered.context["tenants"]],
            ["Access Expired"],
        )

    def test_creating_past_due_invoice_reconciles_subscription_status(self):
        from apps.tenants.models import (
            BillingInvoice, BillingInvoiceStatus, Plan,
            SubscriptionStatus, TenantSubscription,
        )
        tenant = Tenant.objects.create(name="Past due create", slug="past-due-create")
        TenantSettings.objects.create(tenant=tenant)
        plan = Plan.objects.create(name="Past Due Create Plan", code="past-due-create-plan")
        subscription = TenantSubscription.objects.create(
            tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE,
        )
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        response = self.client.post(url, {
            "create_invoice": "1",
            "inv-invoice_number": "INV-PAST-DUE-CREATE",
            "inv-amount": "50000.00",
            "inv-currency": "UGX",
            "inv-status": BillingInvoiceStatus.PAST_DUE,
            "inv-issued_at": "",
            "inv-due_at": "",
            "inv-paid_at": "",
            "inv-external_ref": "",
            "inv-note": "",
        })
        self.assertRedirects(response, url)
        self.assertTrue(BillingInvoice.objects.filter(
            tenant=tenant,
            invoice_number="INV-PAST-DUE-CREATE",
            status=BillingInvoiceStatus.PAST_DUE,
        ).exists())
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAST_DUE)

    def test_invoice_status_cannot_reverse_from_paid_or_void(self):
        from apps.tenants.models import (
            BillingInvoice, BillingInvoiceStatus, Plan,
            SubscriptionStatus, TenantSubscription,
        )
        tenant = Tenant.objects.create(name="Invoice final states", slug="invoice-final-states")
        TenantSettings.objects.create(tenant=tenant)
        plan = Plan.objects.create(name="Invoice Final Plan", code="invoice-final-plan")
        subscription = TenantSubscription.objects.create(
            tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE,
        )
        paid = BillingInvoice.objects.create(
            tenant=tenant,
            subscription=subscription,
            invoice_number="INV-FINAL-PAID",
            amount="100.00",
            currency="UGX",
            status=BillingInvoiceStatus.PAID,
        )
        void = BillingInvoice.objects.create(
            tenant=tenant,
            subscription=subscription,
            invoice_number="INV-FINAL-VOID",
            amount="100.00",
            currency="UGX",
            status=BillingInvoiceStatus.VOID,
        )
        url = reverse("console-platform-tenant-control-plane", kwargs={"tenant_id": tenant.pk})
        for invoice, target in (
            (paid, BillingInvoiceStatus.DRAFT),
            (void, BillingInvoiceStatus.PAST_DUE),
        ):
            response = self.client.post(url, {
                "invoice_set_status": "1",
                "invoice_id": str(invoice.pk),
                "status": target,
            })
            self.assertRedirects(response, url)
            invoice.refresh_from_db()
            self.assertNotEqual(invoice.status, target)

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Final state", count=2)

    def test_tenant_scope_middleware_precedes_staff_membership_lookup(self):
        from django.conf import settings
        middleware = settings.MIDDLEWARE
        self.assertLess(
            middleware.index("apps.api.middleware.PostgresRequestTenantGucMiddleware"),
            middleware.index("apps.staff.middleware.StaffSessionTenantMiddleware"),
        )
