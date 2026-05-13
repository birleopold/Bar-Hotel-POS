from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.lodging.models import (
    Folio,
    FolioLine,
    FolioStatus,
    Reservation,
    ReservationStatus,
    Room,
    RoomStatus,
    RoomType,
)
from apps.lodging.services import (
    cancel_reservation,
    check_in_reservation,
    check_out_reservation,
    validate_room_available_for_reservation,
)

from .forms import StaffFolioManualLineForm, StaffReservationForm
from .middleware import STAFF_SESSION_SITE_KEY
from .mixins import StaffTenantRequiredMixin
from .services import membership_can_modify_lodging, resolve_staff_site, sites_visible_for_membership


def _flash_drf_validation(request: HttpRequest, exc: DRFValidationError) -> None:
    d = exc.detail
    if isinstance(d, dict):
        for key, val in d.items():
            parts = val if isinstance(val, list) else [val]
            for p in parts:
                messages.error(request, f"{key}: {str(p)}")
    else:
        messages.error(request, str(d))


def _allowed_site_ids(request) -> set[uuid.UUID]:
    return {s.id for s in sites_visible_for_membership(request.tenant_membership)}


def _lodging_sites_and_site(request: HttpRequest):
    sites = sites_visible_for_membership(request.tenant_membership)
    site = resolve_staff_site(request, sites)
    return sites, site


class StaffSelectSiteView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "lodging"

    def post(self, request: HttpRequest) -> HttpResponse:
        sites = sites_visible_for_membership(request.tenant_membership)
        sid = request.POST.get("site_id", "").strip()
        nxt = request.POST.get("next", "").strip() or reverse("staff-lodging-reservations")
        try:
            uid = uuid.UUID(sid)
        except ValueError:
            messages.error(request, "Invalid branch.")
            return redirect(nxt)
        if not any(s.id == uid for s in sites):
            messages.error(request, "You cannot switch to that branch.")
            return redirect(nxt)
        request.session[STAFF_SESSION_SITE_KEY] = str(uid)
        messages.success(request, "Branch updated.")
        return redirect(nxt)


class StaffReservationsListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "lodging"
    template_name = "staff/lodging/reservations_list.html"
    context_object_name = "reservations"
    paginate_by = 40

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _lodging_sites_and_site(request)
        if self.current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = (
            Reservation.objects.filter(
                tenant=self.request.tenant,
                site=self.current_site,
            )
            .select_related("site", "room", "room__room_type")
            .order_by("-check_in", "guest_name")
        )
        st = self.request.GET.get("status")
        if st and st in {c[0] for c in ReservationStatus.choices}:
            qs = qs.filter(status=st)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["status_filter"] = self.request.GET.get("status") or ""
        ctx["can_modify_lodging"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffLodgingAvailabilityView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "lodging"
    template_name = "staff/lodging/availability.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        sites, current_site = _lodging_sites_and_site(request)
        if current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")

        raw_ci = (request.GET.get("check_in") or "").strip()
        raw_co = (request.GET.get("check_out") or "").strip()
        today = date.today()
        ci = parse_date(raw_ci) if raw_ci else today
        co = parse_date(raw_co) if raw_co else (today + timedelta(days=1))

        if ci is None or co is None:
            messages.error(request, "Invalid date range.")
            ci = today
            co = today + timedelta(days=1)
        if co <= ci:
            messages.error(request, "Check-out must be after check-in.")
            co = ci + timedelta(days=1)

        rooms_qs = (
            Room.objects.filter(room_type__site=current_site, is_active=True)
            .select_related("room_type")
            .order_by("room_type__name", "name")
        )
        reserved_room_ids = set(
            Reservation.objects.filter(
                tenant=request.tenant,
                site=current_site,
                room_id__isnull=False,
            )
            .exclude(status=ReservationStatus.CANCELLED)
            .filter(check_in__lt=co, check_out__gt=ci)
            .values_list("room_id", flat=True)
        )
        available = [rm for rm in rooms_qs if rm.id not in reserved_room_ids]
        grouped: dict[str, list[Room]] = {}
        for rm in available:
            grouped.setdefault(rm.room_type.name, []).append(rm)

        return render(
            request,
            self.template_name,
            {
                "sites": sites,
                "current_site": current_site,
                "check_in": ci,
                "check_out": co,
                "available_rooms": available,
                "available_by_type": grouped,
            },
        )


class StaffReservationCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "lodging"
    template_name = "staff/lodging/reservation_form.html"
    form_class = StaffReservationForm

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _lodging_sites_and_site(request)
        if self.current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot create reservations.")
            return redirect("staff-lodging-reservations")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        return ctx

    def form_valid(self, form):
        res = form.save(commit=False)
        res.tenant = self.request.tenant
        res.site = self.current_site
        res.status = ReservationStatus.CONFIRMED
        res.save()
        messages.success(self.request, "Reservation created.")
        return redirect("staff-lodging-reservation-detail", reservation_id=res.id)


class StaffReservationDetailView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "lodging"
    template_name = "staff/lodging/reservation_detail.html"
    context_object_name = "reservation"
    pk_url_kwarg = "reservation_id"
    http_method_names = ["get", "post", "head", "options"]

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _lodging_sites_and_site(request)
        if self.current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        allowed = _allowed_site_ids(self.request)
        return (
            Reservation.objects.filter(tenant=self.request.tenant, site_id__in=allowed)
            .select_related("site", "room", "room__room_type")
            .prefetch_related(
                "folios",
                "folios__lines",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        res: Reservation = ctx["reservation"]
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["can_modify_lodging"] = membership_can_modify_lodging(self.request.tenant_membership)
        ctx["room_choices"] = (
            Room.objects.filter(room_type__site_id=res.site_id, is_active=True)
            .select_related("room_type")
            .order_by("room_type__name", "name")
        )
        open_folio = (
            Folio.objects.filter(reservation=res, status=FolioStatus.OPEN)
            .prefetch_related("lines")
            .first()
        )
        ctx["open_folio"] = open_folio
        ctx["folio_line_form"] = StaffFolioManualLineForm()
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.object = self.get_object()
        res: Reservation = self.object
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot change reservations.")
            return redirect("staff-lodging-reservation-detail", reservation_id=res.id)

        action = request.POST.get("action", "").strip()

        if action == "assign_room":
            rid = request.POST.get("room_id", "").strip()
            if rid == "" or rid == "__none__":
                res.room = None
                res.save(update_fields=["room", "updated_at"])
                messages.success(request, "Room cleared.")
            else:
                try:
                    ru = uuid.UUID(rid)
                except ValueError:
                    messages.error(request, "Invalid room.")
                    return redirect("staff-lodging-reservation-detail", reservation_id=res.id)
                room = Room.objects.filter(
                    pk=ru,
                    room_type__tenant_id=res.tenant_id,
                    room_type__site_id=res.site_id,
                    is_active=True,
                ).first()
                if room is None:
                    messages.error(request, "That room is not available at this branch.")
                else:
                    try:
                        validate_room_available_for_reservation(reservation=res, room=room)
                    except DRFValidationError as e:
                        _flash_drf_validation(request, e)
                    else:
                        res.room = room
                        res.save(update_fields=["room", "updated_at"])
                        messages.success(request, "Room updated.")
            return redirect("staff-lodging-reservation-detail", reservation_id=res.id)

        if action == "check_in":
            try:
                check_in_reservation(reservation=res, user=request.user)
            except DRFValidationError as e:
                _flash_drf_validation(request, e)
            else:
                messages.success(request, "Checked in.")
            return redirect("staff-lodging-reservation-detail", reservation_id=res.id)

        if action == "check_out":
            try:
                check_out_reservation(reservation=res, user=request.user)
            except DRFValidationError as e:
                _flash_drf_validation(request, e)
            else:
                messages.success(request, "Checked out.")
            return redirect("staff-lodging-reservation-detail", reservation_id=res.id)

        if action == "cancel":
            reason = request.POST.get("reason", "")
            try:
                cancel_reservation(reservation=res, user=request.user, reason=reason)
            except DRFValidationError as e:
                _flash_drf_validation(request, e)
            else:
                messages.success(request, "Reservation cancelled.")
            return redirect("staff-lodging-reservation-detail", reservation_id=res.id)

        if action == "open_folio":
            if Folio.objects.filter(reservation=res, status=FolioStatus.OPEN).exists():
                messages.error(request, "An open folio already exists for this stay.")
            else:
                Folio.objects.create(
                    tenant_id=res.tenant_id,
                    site_id=res.site_id,
                    reservation=res,
                    guest_name=res.guest_name,
                    currency="USD",
                    status=FolioStatus.OPEN,
                )
                messages.success(request, "Folio opened.")
            return redirect("staff-lodging-reservation-detail", reservation_id=res.id)

        if action == "folio_line":
            try:
                fid = uuid.UUID(request.POST.get("folio_id", "").strip())
            except ValueError:
                messages.error(request, "Invalid folio.")
                return redirect("staff-lodging-reservation-detail", reservation_id=res.id)
            folio = Folio.objects.filter(
                pk=fid,
                tenant_id=res.tenant_id,
                reservation_id=res.id,
                status=FolioStatus.OPEN,
            ).first()
            if folio is None:
                messages.error(request, "Open folio not found.")
                return redirect("staff-lodging-reservation-detail", reservation_id=res.id)
            form = StaffFolioManualLineForm(request.POST)
            if form.is_valid():
                FolioLine.objects.create(
                    tenant_id=res.tenant_id,
                    folio=folio,
                    description=form.cleaned_data["description"][:512],
                    amount=form.cleaned_data["amount"],
                    tax_amount=form.cleaned_data.get("tax_amount") or 0,
                )
                messages.success(request, "Charge added to folio.")
            else:
                for _field, errs in form.errors.items():
                    for err in errs:
                        messages.error(request, str(err))
            return redirect("staff-lodging-reservation-detail", reservation_id=res.id)

        messages.error(request, "Unknown action.")
        return redirect("staff-lodging-reservation-detail", reservation_id=res.id)


class StaffRoomsListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "lodging"
    template_name = "staff/lodging/rooms_list.html"
    context_object_name = "rooms"

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _lodging_sites_and_site(request)
        if self.current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Room.objects.filter(room_type__site=self.current_site, is_active=True)
            .select_related("room_type", "room_type__site")
            .order_by("room_type__name", "name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        return ctx


class StaffLodgingRoomTypesListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "lodging"
    """Read-only room types and nightly rate windows for the active property."""

    template_name = "staff/lodging/room_types_list.html"
    context_object_name = "room_types"

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _lodging_sites_and_site(request)
        if self.current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            RoomType.objects.filter(site=self.current_site, is_active=True)
            .prefetch_related("rate_windows")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        return ctx


class StaffFolioListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "lodging"
    """Property-scoped folio register (open and closed) with line totals."""

    template_name = "staff/lodging/folios_list.html"
    context_object_name = "folios"
    paginate_by = 40

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _lodging_sites_and_site(request)
        if self.current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = (
            Folio.objects.filter(tenant=self.request.tenant, site=self.current_site)
            .select_related("reservation", "reservation__room", "reservation__room__room_type")
            .annotate(
                lines_subtotal=Coalesce(
                    Sum("lines__amount"),
                    Value(Decimal("0")),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
                lines_tax=Coalesce(
                    Sum("lines__tax_amount"),
                    Value(Decimal("0")),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
            )
            .annotate(
                lines_grand=F("lines_subtotal") + F("lines_tax"),
            )
            .order_by("-created_at")
        )
        st = self.request.GET.get("status")
        if st and st in {c[0] for c in FolioStatus.choices}:
            qs = qs.filter(status=st)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["status_filter"] = self.request.GET.get("status") or ""
        ctx["can_modify_lodging"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffFolioDetailView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "lodging"
    model = Folio
    template_name = "staff/lodging/folio_detail.html"
    context_object_name = "folio"
    pk_url_kwarg = "folio_id"

    def dispatch(self, request, *args, **kwargs):
        self.sites, self.current_site = _lodging_sites_and_site(request)
        if self.current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        allowed = _allowed_site_ids(self.request)
        return (
            Folio.objects.filter(tenant=self.request.tenant, site_id__in=allowed)
            .select_related("site", "reservation", "reservation__room", "reservation__room__room_type")
            .prefetch_related("lines__source_order")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        folio: Folio = ctx["folio"]
        lines = list(folio.lines.all())
        sub = sum((ln.amount for ln in lines), Decimal("0"))
        tax = sum((ln.tax_amount for ln in lines), Decimal("0"))
        ctx["sites"] = self.sites
        ctx["current_site"] = self.current_site
        ctx["lines_subtotal"] = sub
        ctx["lines_tax_total"] = tax
        ctx["lines_grand_total"] = sub + tax
        ctx["can_modify_lodging"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffLodgingTapeChartView(StaffTenantRequiredMixin, View):
    """Lightweight occupancy grid: rooms × dates for the active property (tape-chart style)."""

    staff_nav_capability = "lodging"
    template_name = "staff/lodging/tape_chart.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        sites, current_site = _lodging_sites_and_site(request)
        if current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")

        raw_start = (request.GET.get("start") or "").strip()
        today = date.today()
        start = parse_date(raw_start) if raw_start else today
        if start is None:
            start = today

        horizon_days = 14
        end_exclusive = start + timedelta(days=horizon_days)
        dates = [start + timedelta(days=i) for i in range(horizon_days)]

        rooms = list(
            Room.objects.filter(room_type__site=current_site, is_active=True)
            .select_related("room_type")
            .order_by("room_type__name", "name")
        )
        reservations = (
            Reservation.objects.filter(tenant=request.tenant, site=current_site, room_id__isnull=False)
            .exclude(status=ReservationStatus.CANCELLED)
            .filter(check_in__lt=end_exclusive, check_out__gt=start)
            .select_related("room", "room__room_type")
        )
        occupied: dict[tuple[uuid.UUID, date], Reservation] = {}
        for res in reservations:
            d = res.check_in
            while d < res.check_out and d < end_exclusive:
                if d >= start:
                    occupied[(res.room_id, d)] = res
                d += timedelta(days=1)

        tape_rows = []
        for room in rooms:
            cells = []
            for d in dates:
                cells.append({"date": d, "reservation": occupied.get((room.id, d))})
            tape_rows.append({"room": room, "cells": cells})

        prev_start = start - timedelta(days=horizon_days)
        next_start = start + timedelta(days=horizon_days)

        return render(
            request,
            self.template_name,
            {
                "sites": sites,
                "current_site": current_site,
                "tape_start": start,
                "tape_dates": dates,
                "tape_rows": tape_rows,
                "tape_prev_start": prev_start,
                "tape_next_start": next_start,
                "can_modify_lodging": membership_can_modify_lodging(request.tenant_membership),
            },
        )


class StaffHousekeepingBoardView(StaffTenantRequiredMixin, View):
    """Room status board (clean / dirty / inspected / out of order) for the active property."""

    staff_nav_capability = "lodging"
    http_method_names = ["get", "post", "head", "options"]

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        self.sites, self.current_site = _lodging_sites_and_site(request)
        if self.current_site is None:
            messages.info(request, "No branch is set up for lodging in this workspace.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest) -> HttpResponse:
        rooms = (
            Room.objects.filter(room_type__site=self.current_site, is_active=True)
            .select_related("room_type")
            .order_by("room_type__name", "name")
        )
        by_status: dict[str, list[Room]] = {k: [] for k, _ in RoomStatus.choices}
        for r in rooms:
            by_status.setdefault(r.status, []).append(r)
        status_columns = [(label, by_status.get(key, [])) for key, label in RoomStatus.choices]
        return render(
            request,
            "staff/lodging/housekeeping.html",
            {
                "sites": self.sites,
                "current_site": self.current_site,
                "status_columns": status_columns,
                "room_statuses": RoomStatus.choices,
                "can_modify_lodging": membership_can_modify_lodging(request.tenant_membership),
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot update room status.")
            return redirect("staff-lodging-housekeeping")
        rid = request.POST.get("room_id", "").strip()
        new_status = (request.POST.get("status") or "").strip()
        try:
            uid = uuid.UUID(rid)
        except ValueError:
            messages.error(request, "Invalid room.")
            return redirect("staff-lodging-housekeeping")
        if new_status not in {c[0] for c in RoomStatus.choices}:
            messages.error(request, "Invalid status.")
            return redirect("staff-lodging-housekeeping")
        room = (
            Room.objects.filter(
                id=uid,
                room_type__site=self.current_site,
                room_type__tenant_id=request.tenant.id,
            )
            .select_related("room_type")
            .first()
        )
        if room is None:
            messages.error(request, "Room not found.")
            return redirect("staff-lodging-housekeeping")
        room.status = new_status
        room.save(update_fields=["status", "updated_at"])
        messages.success(request, f"{room.name} is now {room.get_status_display()}.")
        return redirect("staff-lodging-housekeeping")
