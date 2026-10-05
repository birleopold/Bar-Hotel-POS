from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, UpdateView

from apps.integrations.efris import EFRIS_PROVIDER_KEY, get_efris_adapter
from apps.integrations.models import EfrisSubmission, IntegrationLink
from apps.tenants.models import TenantSettings

from .forms import (
    StaffEfrisSettingsForm,
    StaffIntegrationLinkForm,
    StaffTenantBrandingForm,
    StaffTenantModulesForm,
)
from .mixins import StaffTenantRequiredMixin
from .services import (
    get_tenant_staff_modules,
    initial_staff_modules_for_form,
    membership_can_manage_workspace_settings,
    STAFF_MODULE_CHOICES,
)


class StaffWorkspaceModulesView(StaffTenantRequiredMixin, FormView):
    """Turn staff product areas on/off for this tenant (owner / tenant admin)."""

    staff_nav_capability = "workspace"
    template_name = "staff/settings/modules.html"
    form_class = StaffTenantModulesForm
    success_url = reverse_lazy("staff-workspace-modules")

    def dispatch(self, request, *args, **kwargs):
        from apps.staff.services.modules import get_tenant_staff_modules

        if not get_tenant_staff_modules(request.tenant):
            messages.error(request, "Choose an active business area and plan before managing staff modules.")
            return redirect("console-org-setup")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"modules": initial_staff_modules_for_form(self.request.tenant)}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        can = membership_can_manage_workspace_settings(self.request.tenant_membership)
        ctx["can_manage_modules"] = can
        if not can:
            ctx.pop("form", None)
        mods = get_tenant_staff_modules(self.request.tenant)
        labels = dict(STAFF_MODULE_CHOICES)
        order = [k for k, _ in STAFF_MODULE_CHOICES]
        ctx["active_module_labels"] = [
            labels[m] for m in sorted(mods, key=lambda x: order.index(x) if x in order else 99)
        ]
        return ctx

    def post(self, request, *args, **kwargs) -> HttpResponse:
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(
                request,
                "Only an owner or tenant admin can change enabled staff areas.",
            )
            return redirect("staff-workspace-modules")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        ts, _ = TenantSettings.objects.get_or_create(tenant=self.request.tenant)
        ts.enabled_staff_modules = list(form.cleaned_data["modules"])
        ts.save(update_fields=["enabled_staff_modules"])
        messages.success(
            self.request,
            "Staff areas saved. Navigation updates immediately for everyone in this workspace.",
        )
        return redirect(self.success_url)


class StaffWorkspaceBrandingView(StaffTenantRequiredMixin, UpdateView):
    """Branding and regional defaults; edit restricted to owner / tenant admin (not accountant)."""

    staff_nav_capability = "workspace"
    model = TenantSettings
    form_class = StaffTenantBrandingForm
    template_name = "staff/settings/branding.html"
    success_url = reverse_lazy("staff-workspace-branding")

    def get_object(self, queryset=None):
        ts, _ = TenantSettings.objects.get_or_create(tenant=self.request.tenant)
        return ts

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        can = membership_can_manage_workspace_settings(self.request.tenant_membership)
        ctx["can_manage_workspace"] = can
        if not can:
            ctx.pop("form", None)
        return ctx

    def post(self, request, *args, **kwargs) -> HttpResponse:
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(
                request,
                "Only an owner or tenant admin can change workspace branding and defaults.",
            )
            return redirect("staff-workspace-branding")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Workspace settings saved. Staff pages pick up theme on refresh.")
        return super().form_valid(form)


class StaffIntegrationLinkListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "workspace"
    template_name = "staff/settings/integrations_list.html"
    context_object_name = "integration_links"
    paginate_by = 40

    def get_queryset(self):
        return IntegrationLink.objects.filter(tenant=self.request.tenant).order_by("provider_key")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_manage_integrations"] = membership_can_manage_workspace_settings(
            self.request.tenant_membership
        )
        return ctx


class StaffIntegrationLinkCreateView(StaffTenantRequiredMixin, CreateView):
    staff_nav_capability = "workspace"
    model = IntegrationLink
    form_class = StaffIntegrationLinkForm
    template_name = "staff/settings/integration_form.html"
    success_url = reverse_lazy("staff-workspace-integrations")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can add integration links.")
            return redirect("staff-workspace-integrations")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["updating"] = False
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "New integration link"
        return ctx

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.tenant = self.request.tenant
        self.object.save()
        messages.success(self.request, "Integration link created.")
        return redirect(self.success_url)


class StaffIntegrationLinkUpdateView(StaffTenantRequiredMixin, UpdateView):
    staff_nav_capability = "workspace"
    model = IntegrationLink
    form_class = StaffIntegrationLinkForm
    template_name = "staff/settings/integration_form.html"
    pk_url_kwarg = "link_id"
    success_url = reverse_lazy("staff-workspace-integrations")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can edit integration links.")
            return redirect("staff-workspace-integrations")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return IntegrationLink.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["updating"] = True
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Edit integration link"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Integration link updated.")
        return super().form_valid(form)


class StaffEfrisSettingsView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "workspace"
    template_name = "staff/settings/efris_settings.html"
    form_class = StaffEfrisSettingsForm
    success_url = reverse_lazy("staff-workspace-efris")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can manage EFRIS settings.")
            return redirect("staff-workspace-integrations")
        return super().dispatch(request, *args, **kwargs)

    def _tenant_settings(self) -> TenantSettings:
        ts, _ = TenantSettings.objects.get_or_create(tenant=self.request.tenant)
        return ts

    def _efris_link(self) -> IntegrationLink | None:
        return (
            IntegrationLink.objects.filter(
                tenant=self.request.tenant,
                provider_key=EFRIS_PROVIDER_KEY,
            )
            .order_by("created_at")
            .first()
        )

    def get_initial(self):
        return StaffEfrisSettingsForm.build_initial(
            tenant_settings=self._tenant_settings(),
            link=self._efris_link(),
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        link = self._efris_link()
        kwargs["existing_settings"] = (link.settings or {}) if link else {}
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["efris_link"] = self._efris_link()
        ctx["efris_submissions"] = list(
            EfrisSubmission.objects.filter(tenant=self.request.tenant)
            .select_related("cashbook_entry", "cashbook_entry__category")
            .order_by("-created_at")[:50]
        )
        return ctx

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "save").strip().lower()
        self.object = None
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)
        if action == "health_check":
            adapter = get_efris_adapter()
            result = adapter.health_check_settings(settings=form.to_integration_settings())
            if result.success:
                messages.success(
                    request,
                    "EFRIS health check passed. Credentials and endpoint are reachable.",
                )
            else:
                messages.error(request, f"EFRIS health check failed: {result.error_message}")
            return self.render_to_response(self.get_context_data(form=form))
        return self.form_valid(form)

    def form_valid(self, form):
        ts = self._tenant_settings()
        ts.efris_enabled = bool(form.cleaned_data.get("tenant_efris_enabled"))
        ts.save(update_fields=["efris_enabled", "updated_at"])
        link = self._efris_link()
        if link is None:
            link = IntegrationLink(
                tenant=self.request.tenant,
                provider_key=EFRIS_PROVIDER_KEY,
                label="URA EFRIS",
            )
        link.is_enabled = bool(form.cleaned_data.get("link_is_enabled"))
        link.settings = form.to_integration_settings()
        if not link.label:
            link.label = "URA EFRIS"
        link.save()
        messages.success(self.request, "EFRIS settings saved.")
        return redirect(self.success_url)
