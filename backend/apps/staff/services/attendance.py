from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import (
    AttendanceBreak,
    AttendanceShift,
    AttendanceShiftStatus,
    Membership,
)
from apps.audit.services import log_audit
from apps.staff.services.membership import (
    sites_visible_for_membership,
    staff_accessible_outlets,
)
from apps.staff.services.workspace import resolve_staff_outlet, resolve_staff_site


def current_attendance_shift(membership: Membership):
    return (
        AttendanceShift.objects.filter(
            tenant=membership.tenant,
            membership=membership,
            status=AttendanceShiftStatus.OPEN,
        )
        .select_related("site", "outlet")
        .prefetch_related("breaks")
        .first()
    )


def _clock_scope(request):
    membership = request.tenant_membership
    sites = sites_visible_for_membership(membership)
    site = resolve_staff_site(request, sites)
    if site is None:
        raise ValidationError("Choose an authorized branch before clocking in.")
    outlets = staff_accessible_outlets(membership)
    outlet = resolve_staff_outlet(request, outlets)
    if outlet is not None and outlet.site_id != site.pk:
        outlet = None
    return site, outlet


@transaction.atomic
def clock_in(*, request, note=""):
    membership = Membership.objects.select_for_update().get(
        pk=request.tenant_membership.pk,
        tenant=request.tenant,
        is_active=True,
    )
    if AttendanceShift.objects.filter(
        membership=membership,
        status=AttendanceShiftStatus.OPEN,
    ).exists():
        raise ValidationError("You are already clocked in.")
    site, outlet = _clock_scope(request)
    now = timezone.now()
    shift = AttendanceShift.objects.create(
        tenant=request.tenant,
        membership=membership,
        site=site,
        outlet=outlet,
        clock_in_at=now,
        note=(note or "").strip()[:255],
    )
    log_audit(
        tenant_id=request.tenant.pk,
        user_id=request.user.pk,
        action="attendance.clocked_in",
        entity_type="attendance_shift",
        entity_id=str(shift.pk),
        payload={
            "membership_id": str(membership.pk),
            "site_id": str(site.pk),
            "outlet_id": str(outlet.pk) if outlet else "",
            "clock_in_at": now.isoformat(),
        },
        source="staff",
    )
    return shift


@transaction.atomic
def start_break(*, request, note=""):
    shift = (
        AttendanceShift.objects.select_for_update()
        .filter(
            tenant=request.tenant,
            membership=request.tenant_membership,
            status=AttendanceShiftStatus.OPEN,
        )
        .first()
    )
    if shift is None:
        raise ValidationError("Clock in before starting a break.")
    if shift.breaks.filter(ended_at__isnull=True).exists():
        raise ValidationError("A break is already in progress.")
    now = timezone.now()
    item = AttendanceBreak.objects.create(
        shift=shift,
        started_at=now,
        note=(note or "").strip()[:255],
    )
    log_audit(
        tenant_id=request.tenant.pk,
        user_id=request.user.pk,
        action="attendance.break_started",
        entity_type="attendance_break",
        entity_id=str(item.pk),
        payload={"shift_id": str(shift.pk), "started_at": now.isoformat()},
        source="staff",
    )
    return item


@transaction.atomic
def end_break(*, request):
    shift = (
        AttendanceShift.objects.select_for_update()
        .filter(
            tenant=request.tenant,
            membership=request.tenant_membership,
            status=AttendanceShiftStatus.OPEN,
        )
        .first()
    )
    if shift is None:
        raise ValidationError("No open attendance shift.")
    item = (
        AttendanceBreak.objects.select_for_update()
        .filter(shift=shift, ended_at__isnull=True)
        .first()
    )
    if item is None:
        raise ValidationError("No break is in progress.")
    now = timezone.now()
    item.ended_at = now
    item.save(update_fields=["ended_at", "updated_at"])
    log_audit(
        tenant_id=request.tenant.pk,
        user_id=request.user.pk,
        action="attendance.break_ended",
        entity_type="attendance_break",
        entity_id=str(item.pk),
        payload={"shift_id": str(shift.pk), "ended_at": now.isoformat()},
        source="staff",
    )
    return item


@transaction.atomic
def clock_out(*, request, note=""):
    shift = (
        AttendanceShift.objects.select_for_update()
        .filter(
            tenant=request.tenant,
            membership=request.tenant_membership,
            status=AttendanceShiftStatus.OPEN,
        )
        .first()
    )
    if shift is None:
        raise ValidationError("You are not clocked in.")
    if shift.breaks.filter(ended_at__isnull=True).exists():
        raise ValidationError("End the current break before clocking out.")
    now = timezone.now()
    if now <= shift.clock_in_at:
        raise ValidationError("Clock-out time must be after clock-in.")
    shift.clock_out_at = now
    shift.status = AttendanceShiftStatus.PENDING
    if note:
        shift.note = (note or "").strip()[:255]
    shift.save(
        update_fields=["clock_out_at", "status", "note", "updated_at"]
    )
    log_audit(
        tenant_id=request.tenant.pk,
        user_id=request.user.pk,
        action="attendance.clocked_out",
        entity_type="attendance_shift",
        entity_id=str(shift.pk),
        payload={
            "membership_id": str(shift.membership_id),
            "clock_in_at": shift.clock_in_at.isoformat(),
            "clock_out_at": now.isoformat(),
        },
        source="staff",
    )
    return shift


def attendance_duration(shift: AttendanceShift):
    end = shift.clock_out_at or timezone.now()
    gross = max(timedelta(0), end - shift.clock_in_at)
    break_total = timedelta(0)
    for item in shift.breaks.all():
        break_end = item.ended_at or end
        if break_end > item.started_at:
            break_total += break_end - item.started_at
    worked = max(timedelta(0), gross - break_total)
    return {
        "gross": gross,
        "breaks": break_total,
        "worked": worked,
        "gross_hours": round(gross.total_seconds() / 3600, 2),
        "break_hours": round(break_total.total_seconds() / 3600, 2),
        "worked_hours": round(worked.total_seconds() / 3600, 2),
    }
