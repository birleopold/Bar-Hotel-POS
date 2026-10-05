from __future__ import annotations

import uuid

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.catalog.models import ServiceOffering
from apps.lodging.models import Room, RoomType
from apps.tenants.business_lines import (
    modules_for_business_lines,
    normalize_business_lines,
    outlet_types_for_business_lines,
)
from apps.tenants.models import Outlet, Site, TenantSettings, TenantSetupProgress

from .forms import (
    ConsoleBusinessProfileForm,
    ConsoleOutletForm,
    ConsoleRoomForm,
    ConsoleRoomTypeForm,
    ConsoleSiteForm,
)
from .mixins import ConsoleOrgAdminRequiredMixin
from .setup_flow import (
    build_tenant_setup_state,
    set_tenant_setup_step_state,
    sync_tenant_setup_progress,
)
from .services import console_business_line_flags


class OrgOverviewView(ConsoleOrgAdminRequiredMixin, TemplateView):
    template_name = "console/org/overview.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        ctx.update(console_business_line_flags(tenant, legacy_defaults=False))
        site_count = Site.objects.filter(tenant=tenant).count()
        outlet_count = Outlet.objects.filter(site__tenant=tenant).count()
        ctx["site_count"] = site_count
        ctx["outlet_count"] = outlet_count
        ctx["room_type_count"] = RoomType.objects.filter(tenant=tenant).count()
        ctx["room_count"] = Room.objects.filter(room_type__tenant=tenant).count()
        ctx["service_count"] = ServiceOffering.objects.filter(tenant=tenant, is_active=True).count()
        progress, _ = TenantSetupProgress.objects.get_or_create(tenant=tenant)
        state = build_tenant_setup_state(tenant, progress=progress)
        progress = sync_tenant_setup_progress(tenant, state)
        ctx["show_setup_prompt"] = not state["setup_complete"]
        ctx["setup_state"] = state
        ctx["setup_progress"] = progress
        ctx["setup_url"] = reverse("console-org-setup")
        ctx["setup_action_url"] = reverse("console-org-setup-step-state")
        return ctx


class OrgSetupWizardView(ConsoleOrgAdminRequiredMixin, TemplateView):
    """Guided first-run setup for property/outlet/menu foundations."""

    template_name = "console/org/setup_wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        ctx.update(console_business_line_flags(tenant, legacy_defaults=False))
        progress, _ = TenantSetupProgress.objects.get_or_create(tenant=tenant)
        state = build_tenant_setup_state(tenant, progress=progress)
        progress = sync_tenant_setup_progress(tenant, state)
        ctx["setup_state"] = state
        ctx["setup_steps"] = state["required_steps"]
        ctx["setup_optional_steps"] = state["optional_steps"]
        ctx["setup_complete"] = state["setup_complete"]
        ctx["next_step"] = state["next_step"]
        ctx["setup_completion_percent"] = state["required_completion_percent"]
        ctx["go_live_checks"] = state["go_live_checks"]
        ctx["go_live_ready"] = state["go_live_ready"]
        ctx["setup_progress"] = progress
        ctx["setup_action_url"] = reverse("console-org-setup-step-state")
        try:
            initial_lines = normalize_business_lines(tenant.settings.business_lines)
        except TenantSettings.DoesNotExist:
            initial_lines = []
        if initial_lines and set(initial_lines) <= {"retail", "supermarket"}:
            ctx["setup_pitch"] = "Configure your catalog, checkout, inventory, and purchasing workflows."
        elif initial_lines == ["lodging"]:
            ctx["setup_pitch"] = "Configure rooms, reservations, housekeeping, and guest account workflows."
        elif initial_lines and set(initial_lines) <= {"bar", "lounge", "restaurant", "cafeteria", "kitchen"}:
            ctx["setup_pitch"] = "Configure your menu, order flow, prep stations, and service operations."
        elif initial_lines == ["services"]:
            ctx["setup_pitch"] = "Configure your services, packages, and appointment sales workflow."
        elif initial_lines == ["events"]:
            ctx["setup_pitch"] = "Configure your event spaces, bookings, and sales workflow."
        else:
            ctx["setup_pitch"] = "Complete the setup steps for the services enabled in this workspace."
        ctx.setdefault(
            "business_profile_form",
            ConsoleBusinessProfileForm(initial={"business_lines": initial_lines}),
        )
        return ctx

    def post(self, request, *args, **kwargs):
        form = ConsoleBusinessProfileForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(business_profile_form=form))
        settings_obj, _ = TenantSettings.objects.get_or_create(tenant=request.tenant)
        lines = form.cleaned_data["business_lines"]
        settings_obj.business_lines = lines
        settings_obj.enabled_staff_modules = modules_for_business_lines(lines)
        settings_obj.save(
            update_fields=["business_lines", "enabled_staff_modules", "updated_at"]
        )
        messages.success(
            request,
            "Business services saved. Staff and administration now show only the selected areas.",
        )
        return redirect("console-org-setup")


class OrgSetupStepStateView(ConsoleOrgAdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        step_key = (request.POST.get("step_key") or "").strip()
        state = (request.POST.get("state") or "").strip().lower()
        next_url = (request.POST.get("next") or "").strip() or reverse("console-org-setup")
        try:
            set_tenant_setup_step_state(
                request.tenant,
                step_key=step_key,
                state=state,
            )
        except ValueError:
            messages.error(request, "Invalid setup step action.")
        else:
            if state in {"skipped", "blocked"}:
                messages.success(request, "Setup step state updated.")
            else:
                messages.success(request, "Setup step reset.")
        return redirect(next_url)


class OrgSiteListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/site_list.html"
    context_object_name = "sites"

    def get_queryset(self):
        return Site.objects.filter(tenant=self.request.tenant).order_by("name")


class OrgSiteCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = Site
    form_class = ConsoleSiteForm
    template_name = "console/org/site_form.html"

    def get_success_url(self):
        return reverse("console-org-sites")

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        messages.success(self.request, f"Property “{form.instance.name}” created.")
        return super().form_valid(form)


class OrgSiteUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = Site
    form_class = ConsoleSiteForm
    template_name = "console/org/site_form.html"
    pk_url_kwarg = "site_id"

    def get_queryset(self):
        return Site.objects.filter(tenant=self.request.tenant)

    def get_success_url(self):
        return reverse("console-org-sites")

    def form_valid(self, form):
        messages.success(self.request, f"Property “{form.instance.name}” saved.")
        return super().form_valid(form)


class OrgOutletListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/outlet_list.html"
    context_object_name = "outlets"

    def dispatch(self, request, *args, **kwargs):
        self.site = get_object_or_404(Site, pk=kwargs["site_id"], tenant=request.tenant)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        try:
            lines = normalize_business_lines(self.request.tenant.settings.business_lines)
        except TenantSettings.DoesNotExist:
            lines = []
        qs = Outlet.objects.filter(site=self.site)
        qs = qs.filter(outlet_type__in=outlet_types_for_business_lines(lines))
        return qs.order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["site"] = self.site
        return ctx


class OrgOutletCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = Outlet
    form_class = ConsoleOutletForm
    template_name = "console/org/outlet_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.site = get_object_or_404(Site, pk=kwargs["site_id"], tenant=request.tenant)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("console-org-outlets", kwargs={"site_id": self.site.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        form.instance.site = self.site
        messages.success(self.request, f"Outlet “{form.instance.name}” created.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["site"] = self.site
        return ctx


class OrgOutletUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = Outlet
    form_class = ConsoleOutletForm
    template_name = "console/org/outlet_form.html"
    pk_url_kwarg = "outlet_id"

    def get_queryset(self):
        try:
            lines = normalize_business_lines(self.request.tenant.settings.business_lines)
        except TenantSettings.DoesNotExist:
            lines = []
        qs = Outlet.objects.filter(site__tenant=self.request.tenant)
        qs = qs.filter(outlet_type__in=outlet_types_for_business_lines(lines))
        return qs

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def get_success_url(self):
        return reverse("console-org-outlets", kwargs={"site_id": self.object.site_id})

    def form_valid(self, form):
        messages.success(self.request, f"Outlet “{form.instance.name}” saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["site"] = self.object.site
        return ctx


def _site_ids_for_tenant(tenant) -> list[uuid.UUID]:
    return list(Site.objects.filter(tenant=tenant).values_list("pk", flat=True))


class OrgRoomTypeListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/room_type_list.html"
    context_object_name = "room_types"

    def get_queryset(self):
        return (
            RoomType.objects.filter(tenant=self.request.tenant)
            .select_related("site")
            .order_by("site__name", "name")
        )


class OrgRoomTypeCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = RoomType
    form_class = ConsoleRoomTypeForm
    template_name = "console/org/room_type_form.html"
    success_url = reverse_lazy("console-org-room-types")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["allowed_site_ids"] = _site_ids_for_tenant(self.request.tenant)
        return kw

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        messages.success(self.request, f"Room type “{form.instance.name}” created.")
        return super().form_valid(form)


class OrgRoomTypeUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = RoomType
    form_class = ConsoleRoomTypeForm
    template_name = "console/org/room_type_form.html"
    pk_url_kwarg = "room_type_id"
    success_url = reverse_lazy("console-org-room-types")

    def get_queryset(self):
        return RoomType.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["allowed_site_ids"] = _site_ids_for_tenant(self.request.tenant)
        return kw

    def form_valid(self, form):
        messages.success(self.request, f"Room type “{form.instance.name}” saved.")
        return super().form_valid(form)


class OrgRoomListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/room_list.html"
    context_object_name = "rooms"

    def get_queryset(self):
        return (
            Room.objects.filter(room_type__tenant=self.request.tenant)
            .select_related("room_type", "room_type__site")
            .order_by("room_type__site__name", "room_type__name", "name")
        )


class OrgRoomCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = Room
    form_class = ConsoleRoomForm
    template_name = "console/org/room_form.html"
    success_url = reverse_lazy("console-org-rooms")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        rt_ids = list(
            RoomType.objects.filter(tenant=self.request.tenant).values_list("pk", flat=True),
        )
        kw["tenant"] = self.request.tenant
        kw["allowed_room_type_ids"] = rt_ids
        return kw

    def form_valid(self, form):
        rt = form.cleaned_data["room_type"]
        if rt.tenant_id != self.request.tenant.id:
            raise Http404
        messages.success(self.request, f"Room “{form.instance.name}” created.")
        return super().form_valid(form)


class OrgRoomUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = Room
    form_class = ConsoleRoomForm
    template_name = "console/org/room_form.html"
    pk_url_kwarg = "room_id"
    success_url = reverse_lazy("console-org-rooms")

    def get_queryset(self):
        return Room.objects.filter(room_type__tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        rt_ids = list(
            RoomType.objects.filter(tenant=self.request.tenant).values_list("pk", flat=True),
        )
        kw["tenant"] = self.request.tenant
        kw["allowed_room_type_ids"] = rt_ids
        return kw

    def form_valid(self, form):
        rt = form.cleaned_data["room_type"]
        if rt.tenant_id != self.request.tenant.id:
            raise Http404
        messages.success(self.request, f"Room “{form.instance.name}” saved.")
        return super().form_valid(form)
