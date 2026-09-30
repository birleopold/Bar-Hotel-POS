from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import FormView, ListView, TemplateView, UpdateView

from apps.events.models import EventBooking, EventBookingStatus, EventSpace

from .forms import StaffEventBookingForm, StaffEventSpaceForm
from .mixins import StaffTenantRequiredMixin
from .services import membership_can_modify_lodging, resolve_staff_site, sites_visible_for_membership


def _events_sites_and_site(request: HttpRequest):
    sites = sites_visible_for_membership(request.tenant_membership)
    site = resolve_staff_site(request, sites)
    return sites, site


def _events_site_querysets(request):
    sites, current_site = _events_sites_and_site(request)
    return sites, current_site


class StaffEventSpaceListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "events"
    template_name = "staff/events/spaces_list.html"
    context_object_name = "spaces"
    paginate_by = 40

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _events_site_querysets(request)
        if self.current_site is None:
            messages.info(request, "No property is available for events in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            EventSpace.objects.filter(tenant=self.request.tenant, site=self.current_site)
            .select_related("site")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["can_modify_events"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffEventSpaceCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "events"
    template_name = "staff/events/space_form.html"
    form_class = StaffEventSpaceForm
    success_url = reverse_lazy("staff-events-spaces")

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _events_site_querysets(request)
        if self.current_site is None:
            messages.info(request, "No property is available for events in this workspace.")
            return redirect("staff-dashboard")
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot create event spaces.")
            return redirect("staff-events-spaces")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["form_title"] = "New function space"
        return ctx

    def form_valid(self, form):
        EventSpace.objects.create(
            tenant=self.request.tenant,
            site=self.current_site,
            name=form.cleaned_data["name"],
            capacity=form.cleaned_data["capacity"],
            is_active=form.cleaned_data.get("is_active", True),
        )
        messages.success(self.request, "Space saved.")
        return super().form_valid(form)


class StaffEventSpaceUpdateView(StaffTenantRequiredMixin, UpdateView):
    staff_nav_capability = "events"
    model = EventSpace
    form_class = StaffEventSpaceForm
    template_name = "staff/events/space_form.html"
    pk_url_kwarg = "space_id"
    success_url = reverse_lazy("staff-events-spaces")

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _events_site_querysets(request)
        if self.current_site is None:
            messages.info(request, "No property is available for events in this workspace.")
            return redirect("staff-dashboard")
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot edit event spaces.")
            return redirect("staff-events-spaces")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return EventSpace.objects.filter(tenant=self.request.tenant, site=self.current_site).select_related(
            "site"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["form_title"] = "Edit function space"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Space updated.")
        return super().form_valid(form)


class StaffEventBookingListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "events"
    template_name = "staff/events/bookings_list.html"
    context_object_name = "bookings"
    paginate_by = 30

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _events_site_querysets(request)
        if self.current_site is None:
            messages.info(request, "No property is available for events in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = (
            EventBooking.objects.filter(tenant=self.request.tenant, space__site=self.current_site)
            .select_related("space", "space__site")
            .order_by("start_at")
        )
        st = self.request.GET.get("status")
        if st and st in {c[0] for c in EventBookingStatus.choices}:
            qs = qs.filter(status=st)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["status_filter"] = self.request.GET.get("status") or ""
        ctx["can_modify_events"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffEventBookingCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "events"
    template_name = "staff/events/booking_form.html"
    form_class = StaffEventBookingForm

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _events_site_querysets(request)
        if self.current_site is None:
            messages.info(request, "No property is available for events in this workspace.")
            return redirect("staff-dashboard")
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot create bookings.")
            return redirect("staff-events-bookings")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["event_site"] = self.current_site
        kw["membership"] = self.request.tenant_membership
        kw["user"] = self.request.user
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["form_title"] = "New booking"
        return ctx

    def form_valid(self, form):
        b = form.save(commit=False)
        b.tenant = self.request.tenant
        b.save()
        messages.success(self.request, "Booking created.")
        return redirect("staff-events-booking-detail", booking_id=b.id)


class StaffEventBookingUpdateView(StaffTenantRequiredMixin, UpdateView):
    staff_nav_capability = "events"
    model = EventBooking
    form_class = StaffEventBookingForm
    template_name = "staff/events/booking_detail.html"
    pk_url_kwarg = "booking_id"
    context_object_name = "booking"

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _events_site_querysets(request)
        if self.current_site is None:
            messages.info(request, "No property is available for events in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            EventBooking.objects.filter(tenant=self.request.tenant, space__site=self.current_site)
            .select_related("space", "space__site")
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["event_site"] = self.current_site
        kw["membership"] = self.request.tenant_membership
        kw["user"] = self.request.user
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        can = membership_can_modify_lodging(self.request.tenant_membership)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["can_modify_events"] = can
        if not can:
            ctx.pop("form", None)
        return ctx

    def post(self, request, *args, **kwargs):
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot edit bookings.")
            return redirect("staff-events-booking-detail", booking_id=kwargs[self.pk_url_kwarg])
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Booking saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("staff-events-booking-detail", kwargs={"booking_id": self.object.pk})


class StaffEventCalendarView(StaffTenantRequiredMixin, TemplateView):
    staff_nav_capability = "events"
    template_name = "staff/events/calendar_week.html"

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _events_site_querysets(request)
        if self.current_site is None:
            messages.info(request, "No property is available for events in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        week_raw = self.request.GET.get("week")
        start = parse_date(week_raw) if week_raw else timezone.localdate()
        if start is None:
            start = timezone.localdate()
        monday = start - timedelta(days=start.weekday())
        week_end_excl = monday + timedelta(days=7)
        start_dt = timezone.make_aware(datetime.combine(monday, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(week_end_excl, datetime.min.time()))
        bookings = (
            EventBooking.objects.filter(
                tenant=self.request.tenant,
                space__site=self.current_site,
            )
            .exclude(status=EventBookingStatus.CANCELLED)
            .filter(start_at__lt=end_dt, end_at__gt=start_dt)
            .select_related("space")
            .order_by("start_at")
        )
        prev_week = (monday - timedelta(days=7)).isoformat()
        next_week = (monday + timedelta(days=7)).isoformat()
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["week_start"] = monday
        ctx["bookings"] = bookings
        ctx["prev_week"] = prev_week
        ctx["next_week"] = next_week
        ctx["can_modify_events"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx
