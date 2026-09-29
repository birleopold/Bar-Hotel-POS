from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import Membership
from apps.console.setup_flow import build_tenant_setup_state, sync_tenant_setup_progress
from apps.console.mixins import membership_can_manage_org_console, user_is_platform_operator
from apps.tenants.models import TenantSetupProgress

from .forms import StaffLoginForm
from .middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_SITE_KEY, STAFF_SESSION_TENANT_KEY
from .services import (
    get_tenant_staff_modules,
    membership_queryset_for,
    outlets_visible_for_site,
    resolve_staff_outlet,
    sites_visible_for_membership,
    staff_accessible_outlets,
    staff_dashboard_actions,
    staff_nav_visibility_scoped,
    staff_action_overrides_for_tenant,
)
from .services.dashboard_insights import (
    dashboard_lodging_snapshot,
    dashboard_low_stock_snapshot,
    dashboard_operations_snapshot,
    dashboard_sales_snapshot,
)
from .services.workbench import build_workbench_playbook, role_at_work_copy


class StaffLoginView(LoginView):
    template_name = "staff/login.html"
    form_class = StaffLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form) -> HttpResponse:
        response = super().form_valid(form)
        user = form.get_user()
        first = membership_queryset_for(user).first()
        if first:
            self.request.session[STAFF_SESSION_TENANT_KEY] = str(first.tenant_id)
            if not getattr(first.tenant, "is_active", True):
                return redirect("staff-pending-approval")
        return response


class StaffLogoutView(LogoutView):
    next_page = reverse_lazy("staff-login")


class StaffDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "staff/dashboard.html"
    login_url = reverse_lazy("staff-login")

    def dispatch(self, request: HttpRequest, *args, **kwargs):
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
                action_overrides=staff_action_overrides_for_tenant(active.tenant, outlet=current_outlet),
            )
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
        if membership is not None and not getattr(membership.tenant, "is_active", True):
            messages.info(request, "This workspace is pending platform approval.")
            return redirect("staff-pending-approval")

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
