from __future__ import annotations

import uuid
import time

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import TemplateView
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator

from apps.accounts.models import Membership, MembershipRole
from apps.audit.services import log_audit
from apps.console.setup_flow import build_tenant_setup_state, sync_tenant_setup_progress
from apps.console.mixins import membership_can_manage_org_console, user_is_platform_operator
from apps.tenants.models import OutletType, TenantSetupProgress
from apps.tenants.subscriptions import tenant_operational_access

from .forms import StaffLoginForm, StaffPinSetupForm, StaffTerminalUnlockForm
from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_SITE_KEY, STAFF_SESSION_TENANT_KEY
from .terminal import (
    available_workers, clear_terminal, mark_terminal,
    set_member_pin, terminal_scope, verify_member_pin,
)
from .services import (
    get_tenant_staff_modules,
    membership_queryset_for,
    outlets_visible_for_site,
    resolve_staff_outlet,
    sites_visible_for_membership,
    staff_accessible_outlets,
    staff_dashboard_actions,
    staff_workspace_title,
    staff_nav_visibility_scoped,
    staff_action_overrides_for_tenant,
    staff_outlet_allowed_for_membership,
)
from .services.dashboard_insights import (
    dashboard_lodging_snapshot,
    dashboard_low_stock_snapshot,
    dashboard_operations_snapshot,
    dashboard_sales_snapshot,
)
from .services.workbench import build_workbench_playbook, role_at_work_copy


def _retail_cashier_landing(member, *, outlet_id="", pin_terminal=False) -> str | None:
    """Return the simple retail checkout entry when this sign-in is cashier work.

    Password-authenticated managers keep their management dashboard by default.
    A PIN terminal is explicitly a service terminal, so any authorized worker
    using it lands in checkout when the terminal/outlet is retail.
    """
    if member is None:
        return None
    outlets = staff_accessible_outlets(member)
    retail = [
        outlet for outlet in outlets
        if outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
    ]
    if not retail:
        return None
    if outlet_id and outlet_id != STAFF_SESSION_OUTLET_ALL:
        try:
            selected = uuid.UUID(str(outlet_id))
        except (TypeError, ValueError, AttributeError):
            selected = None
        if selected and any(outlet.pk == selected for outlet in retail):
            return reverse("staff-retail-pos-entry")
    if pin_terminal and len(retail) == len(outlets):
        return reverse("staff-retail-pos-entry")
    if member.role == MembershipRole.SERVER and len(retail) == len(outlets):
        return reverse("staff-retail-pos-entry")
    return None


def login_brand_for_request(request, scope=None):
    """Only a verified domain or signed terminal may select a public identity."""
    from apps.tenants.models import Tenant, TenantSettings

    tenant = getattr(request, "domain_tenant", None)
    # The platform's central hostname is never tenant-branded, even when a
    # previously paired terminal leaves a signed tenant cookie in this browser.
    # Signed terminal scope still governs which workers can unlock via PIN.
    central_hosts = {
        str(host).strip().lower().rstrip(".")
        for host in getattr(settings, "TENANT_CENTRAL_HOSTS", ())
    }
    host = request.get_host().split(":")[0].strip().lower().rstrip(".")
    if host in central_hosts:
        return None
    if tenant is None:
        scope = scope if scope is not None else terminal_scope(request)
        if scope:
            tenant = Tenant.objects.filter(pk=scope[0], is_active=True).first()
    if tenant is None:
        return None
    theme = TenantSettings.objects.filter(tenant=tenant).first()
    from .services.presentation import staff_product_presentation
    presentation = staff_product_presentation(tenant)
    return {
        "name": tenant.name,
        "workspace_label": presentation["workspace_label"],
        "business_key": presentation.get("business_key", ""),
        "logo_url": theme.logo_url if theme else "",
        "favicon_url": (theme.favicon_url or theme.logo_url) if theme else "",
        "background_url": theme.login_background_url if theme else "",
        "welcome_message": theme.login_welcome_message if theme else "",
        "primary": theme.theme_primary if theme else "#173C65",
    }


class StaffLoginView(LoginView):
    template_name = "staff/login.html"
    form_class = StaffLoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["login_brand"] = login_brand_for_request(self.request)
        return context

    def form_valid(self, form) -> HttpResponse:
        # Keep password recovery inside the workspace that opened the shared
        # terminal. Multi-tenant users must set their PIN on that membership.
        scope = terminal_scope(self.request)
        user = form.get_user()
        memberships = membership_queryset_for(user)
        domain_tenant = getattr(self.request, "domain_tenant", None)
        if domain_tenant is not None:
            first = memberships.filter(tenant_id=domain_tenant.pk).first()
            if first is None:
                form.add_error(None, "Unable to sign in to this workspace with those credentials.")
                return self.form_invalid(form)
            if scope is not None and str(scope[0]) != str(domain_tenant.pk):
                scope = None
        else:
            first = memberships.filter(tenant_id=scope[0]).first() if scope else None
        response = super().form_valid(form)
        # A platform operator signing in at the central host enters the
        # platform control plane, not whichever tenant happens to be first.
        # Deliberate, safe "next" links still retain Django's normal behavior.
        central_hosts = {
            str(host).strip().lower().rstrip(".")
            for host in getattr(settings, "TENANT_CENTRAL_HOSTS", ())
        }
        if (
            domain_tenant is None
            and self.request.get_host().split(":")[0].lower().rstrip(".") in central_hosts
            and user_is_platform_operator(user)
        ):
            for key in (
                STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY,
                STAFF_SESSION_SITE_KEY, "staff_pin_session",
                "staff_pin_authenticated", "staff_pin_last_activity",
                "staff_pin_credential", "staff_pin_pairing",
            ):
                self.request.session.pop(key, None)
            response = clear_terminal(response)
            if not self.get_redirect_url():
                response["Location"] = reverse("console-platform-tenants")
            return response
        if first is None and domain_tenant is None:
            first = memberships.first()
            if scope:
                response = clear_terminal(response)
        if first:
            self.request.session[STAFF_SESSION_TENANT_KEY] = str(first.tenant_id)
            access = tenant_operational_access(first.tenant)
            if not access.allowed:
                messages.info(self.request, access.message)
                return redirect("staff-pending-approval")
            if scope and first.tenant_id == scope[0]:
                outlet_id = scope[1]
                if outlet_id == STAFF_SESSION_OUTLET_ALL:
                    self.request.session[STAFF_SESSION_OUTLET_KEY] = STAFF_SESSION_OUTLET_ALL
                elif outlet_id:
                    try:
                        allowed = staff_outlet_allowed_for_membership(first, uuid.UUID(outlet_id))
                    except ValueError:
                        allowed = False
                    if allowed:
                        self.request.session[STAFF_SESSION_OUTLET_KEY] = outlet_id
                    else:
                        self.request.session.pop(STAFF_SESSION_OUTLET_KEY, None)
                        response = clear_terminal(response)
                        messages.error(self.request, "Your account is not assigned to this terminal's outlet. Ask a manager to update your access.")
            if first.staff_pin_hash:
                self.request.session["staff_pin_session"] = True
                self.request.session["staff_pin_last_activity"] = int(time.time())
                self.request.session["staff_pin_credential"] = first.staff_pin_hash
            if not getattr(first.tenant, "is_active", True):
                return redirect("staff-pending-approval")
            if not self.get_redirect_url():
                retail_landing = _retail_cashier_landing(
                    first,
                    outlet_id=self.request.session.get(STAFF_SESSION_OUTLET_KEY, ""),
                    pin_terminal=False,
                )
                if retail_landing:
                    response["Location"] = retail_landing
        return response


class StaffLogoutView(LogoutView):
    next_page = reverse_lazy("staff-login")

    def post(self, request, *args, **kwargs):
        return clear_terminal(super().post(request, *args, **kwargs))


@method_decorator(never_cache, name="dispatch")
class StaffTerminalView(View):
    """Only an authenticated worker can establish this browser as a shared terminal."""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("staff-dashboard")
        scope = terminal_scope(request)
        domain = getattr(request, "domain_tenant", None)
        if domain is not None and (scope is None or str(scope[0]) != str(domain.pk)):
            scope = None
        workers = available_workers(*scope) if scope else []
        form = StaffTerminalUnlockForm(workers=workers)
        return render(request, "staff/terminal.html", {"form": form, "workers": workers, "login_brand": login_brand_for_request(request, scope)})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("staff-dashboard")
        scope = terminal_scope(request)
        domain = getattr(request, "domain_tenant", None)
        if scope is None or (domain is not None and str(scope[0]) != str(domain.pk)):
            return redirect("staff-login")
        workers = available_workers(*scope)
        form = StaffTerminalUnlockForm(request.POST, workers=workers)
        if form.is_valid() and any(m.id == form.cleaned_data["worker"] for m in workers):
            member = verify_member_pin(
                member_id=form.cleaned_data["worker"], tenant_id=scope[0],
                outlet_id=scope[1], pin=form.cleaned_data["pin"],
            )
            if member is not None:
                access = tenant_operational_access(member.tenant)
                if not access.allowed:
                    messages.info(request, access.message)
                    return redirect("staff-login")
                # login() rotates the session key; no previous worker's tenant, outlet,
                # site, or privileges survive the switch.
                logout(request)
                login(request, member.user, backend="django.contrib.auth.backends.ModelBackend")
                request.session[STAFF_SESSION_TENANT_KEY] = str(member.tenant_id)
                if scope[1] and scope[1] != "__all__":
                    request.session[STAFF_SESSION_OUTLET_KEY] = scope[1]
                request.session["staff_pin_session"] = True
                request.session["staff_pin_authenticated"] = True
                request.session["staff_pin_last_activity"] = int(time.time())
                request.session["staff_pin_credential"] = member.staff_pin_hash
                from .workstations import active_pairing
                pair = active_pairing(request, tenant_id=member.tenant_id)
                if pair:
                    request.session["staff_pin_pairing"] = str(pair.pk)
                request.session.set_expiry(0)
                log_audit(tenant_id=member.tenant_id, user_id=member.user_id,
                          action="staff.terminal_unlocked", entity_type="membership", entity_id=str(member.id), payload={})
                retail_landing = _retail_cashier_landing(
                    member,
                    outlet_id=request.session.get(STAFF_SESSION_OUTLET_KEY, ""),
                    pin_terminal=True,
                )
                return redirect(retail_landing or "staff-dashboard")
        form.add_error(None, "Unable to unlock. Check your name and PIN, or sign in with your password.")
        return render(request, "staff/terminal.html", {"form": form, "workers": workers, "login_brand": login_brand_for_request(request, scope)}, status=200)


class StaffTerminalLockView(View):
    def post(self, request):
        membership = getattr(request, "tenant_membership", None)
        if not request.user.is_authenticated:
            return redirect("staff-login")
        if membership is None:
            logout(request)
            return redirect("staff-login")
        tenant_id = membership.tenant_id
        outlet_id = request.session.get(STAFF_SESSION_OUTLET_KEY, "")
        log_audit(tenant_id=tenant_id, user_id=request.user.id,
                  action="staff.terminal_locked", entity_type="membership", entity_id=str(membership.id), payload={})
        logout(request)
        return mark_terminal(redirect("staff-terminal"), tenant_id=tenant_id, outlet_id=outlet_id, request=request)


class StaffPinSetupView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("staff-login")
        if getattr(request, "tenant_membership", None) is None:
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = StaffPinSetupForm(user=request.user)
        return render(request, "staff/pin_setup.html", {"form": form, "has_pin": bool(request.tenant_membership.staff_pin_hash)})

    def post(self, request):
        form = StaffPinSetupForm(request.POST, user=request.user)
        if form.is_valid():
            set_member_pin(request.tenant_membership, form.cleaned_data["pin"])
            request.session["staff_pin_session"] = True
            request.session["staff_pin_last_activity"] = int(time.time())
            request.session["staff_pin_credential"] = request.tenant_membership.staff_pin_hash
            log_audit(tenant_id=request.tenant.id, user_id=request.user.id,
                      action="staff.pin_changed", entity_type="membership",
                      entity_id=str(request.tenant_membership.id), payload={})
            messages.success(request, "Your terminal PIN is ready. Use Lock when you finish serving.")
            return redirect("staff-dashboard")
        return render(request, "staff/pin_setup.html", {"form": form, "has_pin": bool(request.tenant_membership.staff_pin_hash)})


class StaffHelpView(LoginRequiredMixin, TemplateView):
    template_name = "staff/help.html"
    login_url = reverse_lazy("staff-login")

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if getattr(request, "tenant_membership", None) is None:
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)


class StaffDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "staff/dashboard.html"
    login_url = reverse_lazy("staff-login")

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        central_hosts = {
            str(host).strip().lower().rstrip(".")
            for host in getattr(settings, "TENANT_CENTRAL_HOSTS", ())
        }
        if (
            request.user.is_authenticated
            and user_is_platform_operator(request.user)
            and request.get_host().split(":")[0].lower().rstrip(".") in central_hosts
        ):
            return redirect("console-platform-tenants")
        response = super().dispatch(request, *args, **kwargs)
        active = getattr(request, "tenant_membership", None)
        if active is not None and not getattr(active.tenant, "is_active", True):
            return redirect("staff-pending-approval")
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        memberships = list(membership_queryset_for(user))
        ctx["memberships"] = memberships
        ctx["show_console_entry"] = user_is_platform_operator(user)

        session_tid = self.request.session.get(STAFF_SESSION_TENANT_KEY)
        active: Membership | None = None
        if session_tid:
            try:
                u = uuid.UUID(str(session_tid))
                active = next((m for m in memberships if m.tenant_id == u), None)
            except ValueError:
                pass
        if active is None and memberships:
            active = memberships[0]
            self.request.session[STAFF_SESSION_TENANT_KEY] = str(active.tenant_id)

        ctx["active_membership"] = active
        ctx["sites_with_outlets"] = []
        ctx["show_workspace_setup_cta"] = False
        ctx["tenant_setup_state"] = None
        ctx["tenant_setup_progress"] = None
        ctx["tenant_setup_url"] = reverse("console-org-setup")
        ctx["tenant_setup_dismiss_url"] = reverse("staff-setup-prompt-dismiss")
        ctx["tenant_setup_resume_url"] = reverse("staff-setup-prompt-resume")
        ctx["show_workspace_admin_tools"] = False
        ctx["staff_workbench_playbook"] = ()
        ctx["staff_role_at_work"] = ()
        ctx["staff_dashboard_low_stock_rows"] = ()
        ctx["staff_dashboard_low_stock_url"] = ""
        ctx["staff_dashboard_sales_snapshot"] = None
        ctx["staff_dashboard_lodging_snapshot"] = None
        ctx["staff_dashboard_operations_snapshot"] = ()

        if active:
            ctx["show_console_entry"] = user_is_platform_operator(user) or membership_can_manage_org_console(active)
            allowed_ids = {o.id for o in staff_accessible_outlets(active)}
            for site in sites_visible_for_membership(active):
                olist = [o for o in outlets_visible_for_site(active, site) if o.id in allowed_ids]
                ctx["sites_with_outlets"].append(
                    {
                        "site": site,
                        "outlets": olist,
                    }
                )

            outlets = staff_accessible_outlets(active)
            current_outlet = resolve_staff_outlet(self.request, outlets)
            modules = get_tenant_staff_modules(active.tenant, outlet=current_outlet)
            vis = staff_nav_visibility_scoped(active, modules=modules, tenant=active.tenant, outlet=current_outlet)
            sites = sites_visible_for_membership(active)
            pos_shell = (
                ("pos" in modules and (vis.orders or vis.tables or vis.menu or vis.sales))
                or ("kitchen" in modules and vis.kitchen)
            )
            show_ops_nav = bool(outlets) and pos_shell
            show_lodging_nav = bool(sites) and vis.lodging
            primary, secondary = staff_dashboard_actions(
                membership=active,
                vis=vis,
                modules=modules,
                show_lodging_nav=show_lodging_nav,
                show_ops_nav=show_ops_nav,
                outlet=current_outlet,
                action_overrides=staff_action_overrides_for_tenant(active.tenant, outlet=current_outlet),
            )
            ctx["staff_workspace_title"] = staff_workspace_title(active, current_outlet)
            ctx["staff_dashboard_primary_actions"] = primary
            ctx["staff_dashboard_secondary_actions"] = secondary
            can_manage_console = membership_can_manage_org_console(active)
            ctx["show_workspace_admin_tools"] = can_manage_console
            ctx["staff_workbench_playbook"] = build_workbench_playbook(
                vis=vis,
                modules=modules,
                show_lodging_nav=show_lodging_nav,
                show_ops_nav=show_ops_nav,
                membership_role=active.role,
            )
            ctx["staff_role_at_work"] = role_at_work_copy(active.role)
            low_rows, low_url = dashboard_low_stock_snapshot(
                self.request,
                membership=active,
                modules=modules,
                vis_inventory=vis.inventory,
            )
            ctx["staff_dashboard_low_stock_rows"] = low_rows
            ctx["staff_dashboard_low_stock_url"] = low_url
            ctx["staff_dashboard_sales_snapshot"] = dashboard_sales_snapshot(
                self.request,
                membership=active,
                modules=modules,
                vis_sales=vis.sales,
            )
            ctx["staff_dashboard_lodging_snapshot"] = dashboard_lodging_snapshot(
                self.request,
                membership=active,
                visible=show_lodging_nav,
            )
            ctx["staff_dashboard_operations_snapshot"] = dashboard_operations_snapshot(
                self.request,
                membership=active,
                modules=modules,
                vis=vis,
            )
            if can_manage_console:
                setup_state = build_tenant_setup_state(active.tenant)
                setup_progress = sync_tenant_setup_progress(active.tenant, setup_state)
                ctx["tenant_setup_state"] = setup_state
                # Each owner checklist row reflects a real prerequisite, never a
                # fabricated six-step completion percentage.
                setup_steps_by_key = {
                    step["key"]: step
                    for step in setup_state["all_steps"]
                }
                ctx["grocery_setup_checks"] = {
                    "business": bool(setup_steps_by_key.get("business_profile", {}).get("done")),
                    "products": bool(setup_steps_by_key.get("first_sellable", {}).get("done")),
                    "stock": bool(setup_steps_by_key.get("first_stock_receive", {}).get("done")),
                    "staff": bool(setup_steps_by_key.get("first_team_invite", {}).get("done")),
                    "register": bool(setup_steps_by_key.get("first_workstation", {}).get("done")),
                    "sale": bool(setup_steps_by_key.get("first_paid_order", {}).get("done")),
                }
                ctx["tenant_setup_progress"] = setup_progress
                ctx["show_workspace_setup_cta"] = (
                    not setup_state["setup_complete"] and not setup_progress.suppress_dashboard_prompt
                )
            else:
                ctx["show_workspace_setup_cta"] = False
        else:
            ctx["staff_dashboard_primary_actions"] = []
            ctx["staff_dashboard_secondary_actions"] = []
            ctx["staff_dashboard_low_stock_rows"] = ()
            ctx["staff_dashboard_low_stock_url"] = ""
            ctx["staff_dashboard_sales_snapshot"] = None
            ctx["staff_dashboard_lodging_snapshot"] = None
            ctx["staff_dashboard_operations_snapshot"] = ()

        return ctx


class StaffPendingApprovalView(LoginRequiredMixin, TemplateView):
    template_name = "staff/pending_approval.html"
    login_url = reverse_lazy("staff-login")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        memberships = list(membership_queryset_for(user))
        ctx["memberships"] = memberships
        active = getattr(self.request, "tenant_membership", None)
        if active is None:
            session_tid = self.request.session.get(STAFF_SESSION_TENANT_KEY)
            if session_tid:
                try:
                    u = uuid.UUID(str(session_tid))
                    active = next((m for m in memberships if m.tenant_id == u), None)
                except ValueError:
                    active = None
        if active is None and memberships:
            active = memberships[0]
        ctx["active_membership"] = active
        if active is not None:
            access = tenant_operational_access(active.tenant)
            ctx["workspace_access_reason"] = access.reason
            ctx["workspace_access_message"] = access.message
        else:
            ctx["workspace_access_reason"] = ""
            ctx["workspace_access_message"] = ""
        return ctx


class StaffSelectTenantView(LoginRequiredMixin, View):
    login_url = reverse_lazy("staff-login")

    def post(self, request: HttpRequest) -> HttpResponse:
        tid = request.POST.get("tenant_id", "").strip()
        try:
            tenant_uuid = uuid.UUID(tid)
        except ValueError:
            messages.error(request, "Invalid workspace.")
            return redirect("staff-dashboard")

        if (request.session.get("staff_pin_authenticated")
                and str(tenant_uuid) != request.session.get(STAFF_SESSION_TENANT_KEY)):
            messages.error(request, "Sign in with your account password to change workspace.")
            return redirect("staff-dashboard")

        ok = Membership.objects.filter(
            user=request.user,
            tenant_id=tenant_uuid,
            is_active=True,
        ).exists()
        if not ok:
            messages.error(request, "You are not a member of that workspace.")
            return redirect("staff-dashboard")

        request.session[STAFF_SESSION_TENANT_KEY] = str(tenant_uuid)
        request.session.pop(STAFF_SESSION_OUTLET_KEY, None)
        request.session.pop(STAFF_SESSION_SITE_KEY, None)
        membership = (
            Membership.objects.filter(user=request.user, tenant_id=tenant_uuid, is_active=True)
            .select_related("tenant")
            .first()
        )
        if membership is not None:
            access = tenant_operational_access(membership.tenant)
            if not access.allowed:
                messages.info(request, access.message)
                return redirect("staff-pending-approval")

        if membership is not None and membership.staff_pin_hash:
            request.session["staff_pin_session"] = True
            request.session["staff_pin_last_activity"] = int(time.time())
            request.session["staff_pin_credential"] = membership.staff_pin_hash
        elif not request.session.get("staff_pin_authenticated"):
            request.session.pop("staff_pin_session", None)
            request.session.pop("staff_pin_credential", None)

        messages.success(request, "Workspace updated.")
        return redirect("staff-dashboard")


class StaffSetupPromptDismissView(LoginRequiredMixin, View):
    login_url = reverse_lazy("staff-login")

    def post(self, request: HttpRequest) -> HttpResponse:
        membership = getattr(request, "tenant_membership", None)
        if membership is None:
            messages.info(request, "Choose a workspace first.")
            return redirect("staff-dashboard")
        if not membership_can_manage_org_console(membership):
            messages.error(request, "Only owner or tenant admin can hide setup prompts.")
            return redirect("staff-dashboard")
        progress, _ = TenantSetupProgress.objects.get_or_create(tenant=membership.tenant)
        progress.suppress_dashboard_prompt = True
        progress.save(update_fields=["suppress_dashboard_prompt", "updated_at"])
        messages.success(request, "Setup checklist hidden")
        return redirect("staff-dashboard")


class StaffSetupPromptResumeView(LoginRequiredMixin, View):
    login_url = reverse_lazy("staff-login")

    def post(self, request: HttpRequest) -> HttpResponse:
        membership = getattr(request, "tenant_membership", None)
        if membership is None:
            messages.info(request, "Choose a workspace first.")
            return redirect("staff-dashboard")
        if not membership_can_manage_org_console(membership):
            messages.error(request, "Only owner or tenant admin can show setup prompts.")
            return redirect("staff-dashboard")
        progress, _ = TenantSetupProgress.objects.get_or_create(tenant=membership.tenant)
        progress.suppress_dashboard_prompt = False
        progress.save(update_fields=["suppress_dashboard_prompt", "updated_at"])
        messages.success(request, "Setup prompt restored.")
        return redirect(reverse("console-org-setup"))
