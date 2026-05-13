"""Post room-night folio lines on check-in using rate windows (no rate → skip night)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from apps.audit.services import log_audit

from .models import Folio, FolioLine, FolioStatus, Reservation, RoomRateWindow


def _iter_stay_nights(check_in: date, check_out: date):
    d = check_in
    while d < check_out:
        yield d
        d += timedelta(days=1)


def nightly_rate_for_room_type(*, room_type_id, on_date: date) -> Decimal | None:
    w = (
        RoomRateWindow.objects.filter(
            room_type_id=room_type_id,
            valid_from__lte=on_date,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on_date))
        .order_by("-valid_from")
        .first()
    )
    return w.nightly_amount if w else None


def post_room_nights_on_check_in(*, reservation: Reservation, user) -> int:
    """
    Create one folio line per night from check-in (inclusive) to check-out (exclusive)
    when a matching rate window exists. Ensures an open folio for the reservation.
    Returns number of lines created.
    """
    if reservation.room_id is None:
        return 0
    room = reservation.room
    rt_id = room.room_type_id
    folio = (
        Folio.objects.filter(
            reservation=reservation,
            tenant_id=reservation.tenant_id,
            status=FolioStatus.OPEN,
        )
        .first()
    )
    if folio is None:
        folio = Folio.objects.create(
            tenant_id=reservation.tenant_id,
            site_id=reservation.site_id,
            reservation=reservation,
            guest_name=reservation.guest_name,
            currency="USD",
        )
    n_created = 0
    for night in _iter_stay_nights(reservation.check_in, reservation.check_out):
        amt = nightly_rate_for_room_type(room_type_id=rt_id, on_date=night)
        if amt is None:
            continue
        FolioLine.objects.create(
            tenant_id=reservation.tenant_id,
            folio=folio,
            description=f"Room night {night.isoformat()} ({room.name})",
            amount=amt,
            tax_amount=Decimal("0.00"),
        )
        n_created += 1
    if n_created:
        log_audit(
            tenant_id=reservation.tenant_id,
            user_id=user.id if user else None,
            action="lodging.room_nights_posted",
            entity_type="reservation",
            entity_id=str(reservation.id),
            payload={"folio_id": str(folio.id), "lines": n_created},
        )
    return n_created
