from __future__ import annotations

import csv
import io
import uuid
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from rest_framework.exceptions import ValidationError

from apps.accounts.models import (
    AttendanceShift,
    AttendanceShiftStatus,
    MembershipRole,
)
from apps.audit.services import log_audit
from apps.common.datetime_bounds import utc_day_range_inclusive

from .forms import StaffAttendanceActionForm, StaffAttendanceReviewForm
from .mixins import StaffTenantRequiredMixin
from .services.attendance import (
    attendance_duration,
    clock_in,
    clock_out,
    current_attendance_shift,
    end_break,
    start_break,
)
from .services.membership import (
    sites_visible_for_membership,
    staff_accessible_outlets,
)


MANAGER_ROLES = {
    MembershipRole.OWNER,
    MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER,
    MembershipRole.OUTLET_MANAGER,
}


def _format_validation(exc: ValidationError) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return "; ".join(
            f"{key}: {value}" for key, value in detail.items()
        )
    if isinstance(detail, (list, tuple)):
        return "; ".join(str(item) for item in detail)
    return str(detail)


class StaffAttendanceView(StaffTenantRequiredMixin, View):
    template_name = "staff/attendance/my_attendance.html"

    def _context(self, request, form=None):
        shift = current_attendance_shift(request.tenant_membership)
        recent = list(
            AttendanceShift.objects.filter(
                tenant=request.tenant,
                membership=request.tenant_membership,
            )
            .select_related("site", "outlet", "reviewed_by")
            .prefetch_related("breaks")
            .order_by("-clock_in_at")[:10]
        )
        for item in recent:
            item.duration_summary = attendance_duration(item)
        if shift is not None:
            shift.duration_summary = attendance_duration(shift)
            shift.open_break = next(
                (item for item in shift.breaks.all() if item.ended_at is None),
                None,
            )
        return {
            "attendance_shift": shift,
            "recent_attendance": recent,
            "attendance_form": form or StaffAttendanceActionForm(),
            "can_review_timesheets": request.tenant_membership.role in MANAGER_ROLES,
        }

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        form = StaffAttendanceActionForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._context(request, form),
                status=400,
            )
        action = (request.POST.get("action") or "").strip()
        note = form.cleaned_data.get("note") or ""
        try:
            if action == "clock_in":
                clock_in(request=request, note=note)
                messages.success(request, "Clocked in.")
            elif action == "start_break":
                start_break(request=request, note=note)
                messages.success(request, "Break started.")
            elif action == "end_break":
                end_break(request=request)
                messages.success(request, "Break ended.")
            elif action == "clock_out":
                clock_out(request=request, note=note)
                messages.success(request, "Clocked out. Your timesheet is ready for manager review.")
            else:
                return HttpResponse("Unknown attendance action.", status=400)
        except ValidationError as exc:
            messages.error(request, _format_validation(exc))
        return redirect("staff-attendance")


class StaffTimesheetView(StaffTenantRequiredMixin, View):
    template_name = "staff/attendance/timesheets.html"

    def dispatch(self, request, *args, **kwargs):
        if (
            getattr(request, "tenant_membership", None) is not None
            and request.tenant_membership.role not in MANAGER_ROLES
        ):
            return HttpResponseForbidden("Timesheet review is available to managers only.")
        return super().dispatch(request, *args, **kwargs)

    def _scope(self, request):
        sites = sites_visible_for_membership(request.tenant_membership)
        outlets = staff_accessible_outlets(request.tenant_membership)
        return sites, outlets

    def _query(self, request):
        sites, outlets = self._scope(request)
        today = timezone.localdate()
        date_to = parse_date(request.GET.get("date_to") or "") or today
        date_from = parse_date(request.GET.get("date_from") or "") or (date_to - timedelta(days=6))
        if date_from > date_to or (date_to - date_from).days > 31 or date_to > today:
            raise ValidationError("Choose a valid past date range of up to 32 days.")
        start, end = utc_day_range_inclusive(date_from, date_to)
        scope = Q(site_id__in=[site.pk for site in sites])
        outlet_ids = [outlet.pk for outlet in outlets]
        if outlet_ids:
            scope &= Q(outlet__isnull=True) | Q(outlet_id__in=outlet_ids)
        qs = (
            AttendanceShift.objects.filter(
                scope,
                tenant=request.tenant,
                clock_in_at__gte=start,
                clock_in_at__lte=end,
            )
            .select_related(
                "membership__user",
                "site",
                "outlet",
                "reviewed_by",
            )
            .prefetch_related("breaks")
            .order_by("-clock_in_at")
        )
        status_filter = (request.GET.get("status") or "").strip()
        if status_filter in {
            AttendanceShiftStatus.OPEN,
            AttendanceShiftStatus.PENDING,
            AttendanceShiftStatus.APPROVED,
        }:
            qs = qs.filter(status=status_filter)
        worker = (request.GET.get("worker") or "").strip()
        if worker:
            qs = qs.filter(membership_id=worker)
        return qs, date_from, date_to, status_filter, worker

    def _decorate(self, shifts):
        rows = list(shifts)
        for shift in rows:
            shift.duration_summary = attendance_duration(shift)
        return rows

    def get(self, request):
        try:
            qs, date_from, date_to, status_filter, worker = self._query(request)
        except ValidationError as exc:
            return render(
                request,
                self.template_name,
                {
                    "timesheet_error": _format_validation(exc),
                    "timesheets": [],
                    "date_from": "",
                    "date_to": "",
                    "status_filter": "",
                    "worker_filter": "",
                },
                status=400,
            )
        rows = self._decorate(qs)
        if request.GET.get("export") == "csv":
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow([
                "worker",
                "branch",
                "sales_area",
                "clock_in",
                "clock_out",
                "gross_hours",
                "break_hours",
                "worked_hours",
                "status",
                "reviewed_by",
                "review_note",
            ])
            for shift in rows:
                def safe(value):
                    token = str(value or "")
                    return "'" + token if token.startswith(("=", "+", "-", "@", "\t", "\r")) else token
                writer.writerow([
                    safe(shift.membership.user.get_full_name() or shift.membership.user.email),
                    safe(shift.site.name),
                    safe(shift.outlet.name if shift.outlet_id else ""),
                    shift.clock_in_at.isoformat(),
                    shift.clock_out_at.isoformat() if shift.clock_out_at else "",
                    shift.duration_summary["gross_hours"],
                    shift.duration_summary["break_hours"],
                    shift.duration_summary["worked_hours"],
                    shift.status,
                    safe(
                        shift.reviewed_by.get_full_name() or shift.reviewed_by.email
                        if shift.reviewed_by_id else ""
                    ),
                    safe(shift.review_note),
                ])
            response = HttpResponse(out.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="timesheets-{date_from}-{date_to}.csv"'
            )
            response["Cache-Control"] = "private, no-store"
            return response
        worker_options = {}
        for shift in rows:
            worker_options[str(shift.membership_id)] = (
                shift.membership.user.get_full_name()
                or shift.membership.user.email
            )
        return render(
            request,
            self.template_name,
            {
                "timesheets": rows,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "status_filter": status_filter,
                "worker_filter": worker,
                "worker_options": sorted(
                    worker_options.items(),
                    key=lambda item: item[1].lower(),
                ),
            },
        )

    def _scoped_shift(self, request, shift_id):
        try:
            shift_uuid = uuid.UUID(str(shift_id))
        except (ValueError, TypeError, AttributeError):
            raise Http404
        sites, outlets = self._scope(request)
        outlet_ids = [outlet.pk for outlet in outlets]
        scope = Q(site_id__in=[site.pk for site in sites])
        if outlet_ids:
            scope &= Q(outlet__isnull=True) | Q(outlet_id__in=outlet_ids)
        shift = (
            AttendanceShift.objects.select_for_update()
            .filter(scope, tenant=request.tenant, pk=shift_uuid)
            .select_related("membership__user")
            .prefetch_related("breaks")
            .first()
        )
        if shift is None:
            raise Http404
        return shift

    @transaction.atomic
    def post(self, request):
        shift_id = request.POST.get("shift_id")
        shift = self._scoped_shift(request, shift_id)
        if shift.status == AttendanceShiftStatus.OPEN or shift.clock_out_at is None:
            messages.error(request, "Clocked-in shifts cannot be approved or corrected.")
            return redirect(reverse("staff-timesheets"))
        form = StaffAttendanceReviewForm(request.POST)
        if not form.is_valid():
            messages.error(
                request,
                "; ".join(
                    str(error)
                    for errors in form.errors.values()
                    for error in errors
                ),
            )
            return redirect(reverse("staff-timesheets"))

        action = form.cleaned_data["action"]
        before = {
            "clock_in_at": shift.clock_in_at.isoformat(),
            "clock_out_at": shift.clock_out_at.isoformat(),
            "status": shift.status,
            "review_note": shift.review_note,
        }

        if action == "correct":
            new_in = form.cleaned_data["clock_in_at"]
            new_out = form.cleaned_data["clock_out_at"]
            overlap = (
                AttendanceShift.objects.filter(
                    tenant=request.tenant,
                    membership=shift.membership,
                )
                .exclude(pk=shift.pk)
                .filter(clock_in_at__lt=new_out)
                .filter(
                    Q(clock_out_at__gt=new_in)
                    | Q(clock_out_at__isnull=True)
                )
                .exists()
            )
            if overlap:
                messages.error(request, "That correction would overlap another attendance shift.")
                return redirect(reverse("staff-timesheets"))
            for item in shift.breaks.all():
                break_end = item.ended_at or shift.clock_out_at
                if item.started_at < new_in or break_end > new_out:
                    messages.error(
                        request,
                        "Correct the break record first; an existing break would fall outside the proposed shift times.",
                    )
                    return redirect(reverse("staff-timesheets"))
            shift.clock_in_at = new_in
            shift.clock_out_at = new_out

        shift.status = AttendanceShiftStatus.APPROVED
        shift.reviewed_by = request.user
        shift.reviewed_at = timezone.now()
        shift.review_note = (form.cleaned_data.get("review_note") or "").strip()
        shift.save(
            update_fields=[
                "clock_in_at",
                "clock_out_at",
                "status",
                "reviewed_by",
                "reviewed_at",
                "review_note",
                "updated_at",
            ]
        )
        log_audit(
            tenant_id=request.tenant.pk,
            user_id=request.user.pk,
            action=(
                "attendance.timesheet_corrected"
                if action == "correct"
                else "attendance.timesheet_approved"
            ),
            entity_type="attendance_shift",
            entity_id=str(shift.pk),
            payload={
                "membership_id": str(shift.membership_id),
                "before": before,
                "after": {
                    "clock_in_at": shift.clock_in_at.isoformat(),
                    "clock_out_at": shift.clock_out_at.isoformat(),
                    "status": shift.status,
                    "review_note": shift.review_note,
                },
            },
            source="staff",
        )
        messages.success(
            request,
            "Timesheet corrected and approved."
            if action == "correct"
            else "Timesheet approved.",
        )
        return redirect(reverse("staff-timesheets"))
