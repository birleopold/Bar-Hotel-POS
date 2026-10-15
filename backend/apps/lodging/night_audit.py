"""Property night audit: review, reconcile omitted nights, and close explicitly.

Check-in currently pre-posts the full stay. Historical room-night descriptions
are therefore recognized as posted: the auditor must NEVER post them again.
A date close records reconciliation evidence; it does not fabricate card or
cash settlement and does not rewrite historical POS transaction dates.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.tenants.business_date import business_date_for
from apps.pos.models import Order, PosShift, PosShiftStatus

from .models import (
    Folio, FolioLine, FolioStatus, PropertyNightAudit, Reservation,
    ReservationStatus, Room,
)
from .night_charges import nightly_rate_for_room_type


def _night_description(reservation, night):
    return f"Room night {night.isoformat()} ({reservation.room.name})"


def night_audit_snapshot(*, tenant, site, night):
    if site.tenant_id != tenant.pk:
        raise ValidationError({"site": "Property is outside your business."})
    if not isinstance(night, date):
        raise ValidationError({"date": "Choose a valid business date."})

    occupied = list(Reservation.objects.filter(
        tenant=tenant, site=site, status=ReservationStatus.CHECKED_IN,
        check_in__lte=night, check_out__gt=night,
    ).select_related("room", "room__room_type").order_by("guest_name"))
    arrivals = Reservation.objects.filter(
        tenant=tenant, site=site, check_in__lte=night,
        status__in=(ReservationStatus.HELD, ReservationStatus.CONFIRMED),
    ).count()
    departures = Reservation.objects.filter(
        tenant=tenant, site=site, check_out__lte=night,
        status=ReservationStatus.CHECKED_IN,
    ).count()
    open_shifts = PosShift.objects.filter(
        tenant=tenant, outlet__site=site, status=PosShiftStatus.OPEN,
    ).count()
    paid_room_orders = Order.objects.filter(
        tenant=tenant, outlet__site=site, folio__site=site, is_paid=True,
    ).values_list("pk", flat=True)
    linked_order_ids = FolioLine.objects.filter(
        tenant=tenant, folio__site=site, source_order_id__in=paid_room_orders,
    ).values_list("source_order_id", flat=True)
    unmatched_pos_charges = Order.objects.filter(
        tenant=tenant, outlet__site=site, folio__site=site, is_paid=True,
    ).exclude(pk__in=linked_order_ids).count()

    missing = []
    duplicate = []
    for res in occupied:
        if res.room is None:
            missing.append({"reservation_id": str(res.pk), "guest": res.guest_name,
                            "room": "Unassigned", "reason": "Room not assigned", "can_post": False})
            continue
        desc = _night_description(res, night)
        folios = list(Folio.objects.filter(tenant=tenant, site=site, reservation=res).order_by("created_at"))
        count = FolioLine.objects.filter(folio__in=folios, description=desc).count()
        if count > 1:
            duplicate.append({"guest": res.guest_name, "description": desc})
        elif not count:
            active = next((folio for folio in folios if folio.status == FolioStatus.OPEN), None)
            rate = nightly_rate_for_room_type(room_type_id=res.room.room_type_id, on_date=night)
            missing.append({
                "reservation_id": str(res.pk), "guest": res.guest_name,
                "room": res.room.name,
                "reason": ("No open guest folio" if active is None else
                           "Nightly rate missing" if rate is None else "Room night not posted"),
                "rate": str(rate) if rate is not None else None,
                "can_post": active is not None and rate is not None,
            })

    open_folios = Folio.objects.filter(tenant=tenant, site=site, status=FolioStatus.OPEN)
    by_currency = defaultdict(lambda: {"charges": Decimal("0"), "payments": Decimal("0")})
    for folio in open_folios:
        for line in folio.lines.all():
            by_currency[folio.currency]["charges"] += line.amount + line.tax_amount
        for payment in folio.payments.all():
            by_currency[folio.currency]["payments"] += payment.amount
    totals = [
        {"currency": currency, "charges": str(v["charges"]), "payments": str(v["payments"]),
         "outstanding": str(v["charges"] - v["payments"])}
        for currency, v in sorted(by_currency.items())
    ]
    blockers = []
    if arrivals:
        blockers.append(f"{arrivals} pending or missed arrivals")
    if departures:
        blockers.append(f"{departures} departures still checked in")
    if open_shifts:
        blockers.append(f"{open_shifts} registers still have open shifts")
    if unmatched_pos_charges:
        blockers.append(f"{unmatched_pos_charges} paid room-charge orders have no matching folio line")
    if missing:
        blockers.append(f"{len(missing)} room nights need review or posting")
    if duplicate:
        blockers.append(f"{len(duplicate)} room nights have duplicate charges")
    return {
        "date": night.isoformat(), "occupied_count": len(occupied),
        "room_count": Room.objects.filter(room_type__site=site, is_active=True).count(),
        "pending_arrivals": arrivals, "pending_departures": departures,
        "open_shifts": open_shifts, "unmatched_pos_charges": unmatched_pos_charges,
        "missing": missing, "duplicates": duplicate,
        "open_folio_count": open_folios.count(), "currency_totals": totals,
        "blockers": blockers,
    }


@transaction.atomic
def post_missing_room_night(*, tenant, site, night, reservation_id, user):
    """Reconcile a single omitted night without duplicating prepaid stay lines."""
    if site.tenant_id != tenant.pk:
        raise ValidationError({"site": "Property is outside your business."})
    if night > business_date_for(tenant=tenant, site=site):
        raise ValidationError({"date": "Future nights cannot be posted."})
    if PropertyNightAudit.objects.filter(tenant=tenant, site=site, business_date=night).exists():
        raise ValidationError({"date": "This operating date has been closed."})
    res = Reservation.objects.select_for_update().select_related("room", "room__room_type").filter(
        pk=reservation_id, tenant=tenant, site=site, status=ReservationStatus.CHECKED_IN,
        check_in__lte=night, check_out__gt=night,
    ).first()
    if not res or res.room is None:
        raise ValidationError({"reservation": "Select a checked-in guest occupying a room that night."})
    folios = list(Folio.objects.select_for_update().filter(
        tenant=tenant, site=site, reservation=res,
    ).order_by("created_at"))
    desc = _night_description(res, night)
    if FolioLine.objects.filter(folio__in=folios, description=desc).exists():
        return False
    open_folio = next((folio for folio in folios if folio.status == FolioStatus.OPEN), None)
    if not open_folio:
        raise ValidationError({"folio": "Guest needs an open folio before posting."})
    rate = nightly_rate_for_room_type(room_type_id=res.room.room_type_id, on_date=night)
    if rate is None:
        raise ValidationError({"rate": "Set the room type rate for that night before posting."})
    line = FolioLine.objects.create(
        tenant=tenant, folio=open_folio, description=desc,
        amount=rate, tax_amount=Decimal("0.00"),
    )
    log_audit(
        tenant_id=tenant.pk, user_id=user.pk if user else None,
        action="lodging.night_audit_room_posted", entity_type="folio_line", entity_id=str(line.pk),
        payload={"reservation_id": str(res.pk), "night": night.isoformat(), "amount": str(rate)},
    )
    return True


@transaction.atomic
def close_night_audit(*, tenant, site, night, user, note, confirm_cash, confirm_folios):
    """Close only a reviewed business date; repeated requests return the same close."""
    from apps.tenants.models import Site
    locked_site = Site.objects.select_for_update().get(pk=site.pk, tenant=tenant)
    existing = PropertyNightAudit.objects.filter(
        tenant=tenant, site=locked_site, business_date=night,
    ).first()
    if existing:
        return existing, True
    if night > business_date_for(tenant=tenant, site=locked_site):
        raise ValidationError({"date": "Future dates cannot be closed."})
    if not (confirm_cash and confirm_folios):
        raise ValidationError({"confirm": "Confirm register settlement and guest folios first."})
    note = (note or "").strip()
    if len(note) > 512:
        raise ValidationError({"note": "Use at most 512 characters."})
    last = PropertyNightAudit.objects.filter(
        tenant=tenant, site=locked_site,
    ).order_by("-business_date").first()
    if last and night != last.business_date.fromordinal(last.business_date.toordinal() + 1):
        raise ValidationError({"date": "Close operating dates in order; the next date follows the last close."})
    snapshot = night_audit_snapshot(tenant=tenant, site=locked_site, night=night)
    if snapshot["blockers"]:
        raise ValidationError({"detail": "Resolve the listed night audit exceptions before closing."})
    close = PropertyNightAudit.objects.create(
        tenant=tenant, site=locked_site, business_date=night,
        closed_by=user, note=note,
        snapshot={**snapshot, "confirmed_cash": True, "confirmed_folios": True},
    )
    log_audit(
        tenant_id=tenant.pk, user_id=user.pk if user else None,
        action="lodging.night_audit_closed",
        entity_type="property_night_audit", entity_id=str(close.pk),
        payload={"site_id": str(site.pk), "business_date": night.isoformat(),
                 "occupied_count": snapshot["occupied_count"]},
    )
    return close, False
