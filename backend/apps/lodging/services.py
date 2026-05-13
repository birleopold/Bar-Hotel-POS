from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit

from .models import Reservation, ReservationStatus, Room, RoomStatus
from .night_charges import post_room_nights_on_check_in


def validate_room_available_for_reservation(*, reservation: Reservation, room: Room) -> None:
    if room.room_type.site_id != reservation.site_id:
        raise ValidationError({"room": "Room must belong to the same site as the reservation."})

    overlap_exists = (
        Reservation.objects.filter(
            tenant_id=reservation.tenant_id,
            site_id=reservation.site_id,
            room_id=room.id,
        )
        .exclude(id=reservation.id)
        .exclude(status=ReservationStatus.CANCELLED)
        .filter(
            Q(check_in__lt=reservation.check_out) & Q(check_out__gt=reservation.check_in)
        )
        .exists()
    )
    if overlap_exists:
        raise ValidationError({"room": "Room is already assigned for overlapping dates."})


@transaction.atomic
def check_in_reservation(*, reservation: Reservation, user) -> Reservation:
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if reservation.status == ReservationStatus.CANCELLED:
        raise ValidationError({"detail": "Cannot check in a cancelled reservation."})
    if reservation.status == ReservationStatus.CHECKED_OUT:
        raise ValidationError({"detail": "This reservation is already checked out."})
    if reservation.status == ReservationStatus.CHECKED_IN:
        raise ValidationError({"detail": "Already checked in."})
    if reservation.status not in (ReservationStatus.HELD, ReservationStatus.CONFIRMED):
        raise ValidationError({"detail": "Reservation must be held or confirmed to check in."})
    if reservation.room_id is None:
        raise ValidationError({"room": "Assign a room before check-in."})

    validate_room_available_for_reservation(reservation=reservation, room=reservation.room)

    reservation.status = ReservationStatus.CHECKED_IN
    reservation.save(update_fields=["status", "updated_at"])
    post_room_nights_on_check_in(reservation=reservation, user=user)
    log_audit(
        tenant_id=reservation.tenant_id,
        user_id=user.id if user else None,
        action="lodging.check_in",
        entity_type="reservation",
        entity_id=str(reservation.id),
        payload={"guest_name": reservation.guest_name, "room_id": str(reservation.room_id)},
    )
    return reservation


@transaction.atomic
def cancel_reservation(*, reservation: Reservation, user, reason: str = "") -> Reservation:
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if reservation.status == ReservationStatus.CHECKED_OUT:
        raise ValidationError({"detail": "Cannot cancel a checked-out reservation."})
    if reservation.status == ReservationStatus.CANCELLED:
        raise ValidationError({"detail": "Reservation is already cancelled."})
    reservation.status = ReservationStatus.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    log_audit(
        tenant_id=reservation.tenant_id,
        user_id=user.id if user else None,
        action="lodging.cancel",
        entity_type="reservation",
        entity_id=str(reservation.id),
        payload={"guest_name": reservation.guest_name, "reason": (reason or "")[:255]},
    )
    return reservation


@transaction.atomic
def check_out_reservation(*, reservation: Reservation, user) -> Reservation:
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if reservation.status != ReservationStatus.CHECKED_IN:
        raise ValidationError({"detail": "Guest must be checked in to check out."})

    reservation.status = ReservationStatus.CHECKED_OUT
    reservation.save(update_fields=["status", "updated_at"])

    if reservation.room_id:
        room = Room.objects.select_for_update().get(pk=reservation.room_id)
        room.status = RoomStatus.DIRTY
        room.save(update_fields=["status", "updated_at"])

    log_audit(
        tenant_id=reservation.tenant_id,
        user_id=user.id if user else None,
        action="lodging.check_out",
        entity_type="reservation",
        entity_id=str(reservation.id),
        payload={"guest_name": reservation.guest_name},
    )
    return reservation
