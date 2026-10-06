from __future__ import annotations

import uuid

from django.contrib import messages
from django.db.models import Q
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.accounts.models import MembershipRole
from apps.pos.models import KdsLineStatus, Order, OrderLine, OrderStatus
from apps.pos.services import update_order_line_kds_status

from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .services import (
    membership_can_manage_kitchen,
    resolve_staff_outlet,
    staff_accessible_outlets,
    staff_outlet_allowed_for_membership,
)


def _flash_drf_validation(request: HttpRequest, exc: DRFValidationError) -> None:
    d = exc.detail
    if isinstance(d, dict):
        for key, val in d.items():
            parts = val if isinstance(val, list) else [val]
            for p in parts:
                messages.error(request, f"{key}: {str(p)}")
    else:
        messages.error(request, str(d))


def _kds_next_status(current: str) -> str | None:
    nxt = {
        KdsLineStatus.PENDING.value: KdsLineStatus.IN_PREP.value,
        KdsLineStatus.IN_PREP.value: KdsLineStatus.READY.value,
    }
    return nxt.get(current)


def _kds_next_label(current: str) -> str | None:
    labels = {
        KdsLineStatus.PENDING.value: "Start prep",
        KdsLineStatus.IN_PREP.value: "Ready for serving",
    }
    return labels.get(current)


def _line_section(station: str) -> str:
    token = (station or "").strip().lower()
    if token in {"bar", "drinks", "beverage", "bartender"}:
        return "bar"
    if token in {"service", "spa", "steam", "sauna", "lodging", "frontdesk", "front_desk"}:
        return "service"
    return "kitchen"


def _prep_scope_label(role: str) -> str:
    if role == MembershipRole.BARTENDER:
        return "bar"
    if role == MembershipRole.KITCHEN:
        return "kitchen and service"
    return "all prep"


def _bar_station_q() -> Q:
    return (
        Q(kds_station__iexact="bar")
        | Q(kds_station__iexact="drinks")
        | Q(kds_station__iexact="beverage")
        | Q(kds_station__iexact="bartender")
    )


class StaffKdsQueueView(StaffTenantRequiredMixin, View):
    """Open-order lines for kitchen display; requires a single section (not “all”)."""

    staff_nav_capability = "kitchen"
    template_name = "staff/kds/queue.html"

    def _resolve_outlet(self, request: HttpRequest):
        outlets = staff_accessible_outlets(request.tenant_membership)
        if request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
            return None, outlets
        outlet = resolve_staff_outlet(request, outlets)
        if outlet and not staff_outlet_allowed_for_membership(request.tenant_membership, outlet.id):
            return None, outlets
        return outlet, outlets

    def _queue_url(self, station: str) -> str:
        base = reverse("staff-kds")
        if station:
            return f"{base}?station={station}"
        return base

    def get(self, request: HttpRequest) -> HttpResponse:
        outlets = staff_accessible_outlets(request.tenant_membership)
        if not outlets:
            messages.info(request, "You need at least one outlet that matches your role to use the kitchen display.")
            return redirect("staff-dashboard")
        outlet, outlets = self._resolve_outlet(request)
        station = (request.GET.get("station") or "").strip()[:32]

        if outlet is None:
            messages.info(
                request,
                "Kitchen display uses one outlet at a time — pick an outlet above (not “All outlets”).",
            )
            return render(
                request,
                self.template_name,
                {
                    "kds_blocked": True,
                    "outlets": outlets,
                    "current_outlet": None,
                    "station_filter": station,
                    "kds_orders": [],
                    "kds_summary": {"tickets": 0, "lines": 0, "pending": 0, "in_prep": 0, "ready": 0},
                    "can_modify_kds": membership_can_manage_kitchen(request.tenant_membership),
                    "prep_scope_label": _prep_scope_label(request.tenant_membership.role),
                },
            )

        line_qs = (
            OrderLine.objects.filter(is_voided=False)
            .exclude(kds_status=KdsLineStatus.SERVED)
            .select_related("menu_item")
        )
        role = request.tenant_membership.role
        if role == MembershipRole.KITCHEN:
            # Kitchen staff see only prep/service lines; exclude bar queue.
            line_qs = line_qs.exclude(_bar_station_q())
        elif role == MembershipRole.BARTENDER:
            # Bartenders only see bar prep queue.
            line_qs = line_qs.filter(_bar_station_q())
        if station:
            line_qs = line_qs.filter(kds_station=station)

        orders = (
            Order.objects.filter(
                tenant=request.tenant,
                outlet=outlet,
                status=OrderStatus.OPEN,
            )
            .select_related("outlet", "table")
            .prefetch_related(Prefetch("lines", queryset=line_qs.order_by("sort_order", "created_at")))
            .order_by("created_at")
        )

        kds_orders = []
        kds_summary = {"tickets": 0, "lines": 0, "pending": 0, "in_prep": 0, "ready": 0}
        for o in orders:
            lines_out = []
            for ln in o.lines.all():
                kds_summary["lines"] += 1
                if ln.kds_status == KdsLineStatus.PENDING:
                    kds_summary["pending"] += 1
                elif ln.kds_status == KdsLineStatus.IN_PREP:
                    kds_summary["in_prep"] += 1
                elif ln.kds_status == KdsLineStatus.READY:
                    kds_summary["ready"] += 1
                lines_out.append(
                    {
                        "line": ln,
                        "next_status": _kds_next_status(ln.kds_status),
                        "next_label": _kds_next_label(ln.kds_status),
                    }
                )
            if lines_out:
                kds_orders.append({"order": o, "lines": lines_out})
        kds_summary["tickets"] = len(kds_orders)

        return render(
            request,
            self.template_name,
            {
                "kds_blocked": False,
                "outlets": outlets,
                "current_outlet": outlet,
                "station_filter": station,
                "kds_orders": kds_orders,
                "kds_summary": kds_summary,
                "can_modify_kds": membership_can_manage_kitchen(request.tenant_membership),
                "prep_scope_label": _prep_scope_label(request.tenant_membership.role),
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        station = (request.GET.get("station") or request.POST.get("station", "")).strip()[:32]
        outlet, _ = self._resolve_outlet(request)
        if outlet is None:
            messages.error(request, "Select a single outlet first.")
            return redirect(self._queue_url(station))

        if not membership_can_manage_kitchen(request.tenant_membership):
            messages.error(request, "Your role cannot update kitchen prep status.")
            return redirect(self._queue_url(station))

        oid_raw = request.POST.get("order_id", "").strip()
        lid_raw = request.POST.get("line_id", "").strip()
        next_st = request.POST.get("kds_status", "").strip()
        try:
            oid = uuid.UUID(oid_raw)
            lid = uuid.UUID(lid_raw)
        except ValueError:
            messages.error(request, "Invalid order or line.")
            return redirect(self._queue_url(station))

        order = (
            Order.objects.filter(
                pk=oid,
                tenant_id=request.tenant.id,
                outlet_id=outlet.id,
                status=OrderStatus.OPEN,
            )
            .first()
        )
        if order is None:
            messages.error(request, "Order not found or not open at this outlet.")
            return redirect(self._queue_url(station))

        line = OrderLine.objects.filter(pk=lid, order_id=order.id, is_voided=False).first()
        if line is None:
            messages.error(request, "Line not found.")
            return redirect(self._queue_url(station))
        role = request.tenant_membership.role
        section = _line_section(line.kds_station)
        if role == MembershipRole.KITCHEN and section == "bar":
            messages.error(request, "Kitchen staff cannot update bar prep items.")
            return redirect(self._queue_url(station))
        if role == MembershipRole.BARTENDER and section != "bar":
            messages.error(request, "Bar staff can only update bar prep items.")
            return redirect(self._queue_url(station))

        if next_st != _kds_next_status(line.kds_status):
            messages.error(request, "That step is not valid for the current line status.")
            return redirect(self._queue_url(station))

        try:
            update_order_line_kds_status(
                order=order,
                line=line,
                kds_status=next_st,
                kds_station=None,
                user=request.user,
            )
        except DRFValidationError as e:
            _flash_drf_validation(request, e)
        else:
            messages.success(request, f"Updated: {line.label}")

        return redirect(self._queue_url(station))
