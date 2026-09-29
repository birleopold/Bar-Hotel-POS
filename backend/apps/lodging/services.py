from __future__ import annotations

from django.db import transaction
from decimal import Decimal

from django.db.models import Q, Sum
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit

from .models import Folio, FolioPayment, FolioStatus, Reservation, ReservationStatus, Room, RoomStatus
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


def folio_totals(folio: Folio) -> tuple[Decimal, Decimal, Decimal]:
    line_totals = folio.lines.aggregate(amount=Sum("amount"), tax=Sum("tax_amount"))
    charges = (line_totals["amount"] or Decimal("0.00")) + (line_totals["tax"] or Decimal("0.00"))
    paid = folio.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return charges, paid, charges - paid


@transaction.atomic
def record_folio_payment(*, folio: Folio, amount: Decimal, method: str, reference: str, user, idempotency_key: str) -> FolioPayment:
    folio = Folio.objects.select_for_update().get(pk=folio.pk)
    existing = FolioPayment.objects.filter(
        tenant_id=folio.tenant_id,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        return existing
    if folio.status != FolioStatus.OPEN:
        raise ValidationError({"detail": "Payments can only be recorded on an open folio."})
    _charges, _paid, balance = folio_totals(folio)
    if amount <= 0 or amount > balance:
        raise ValidationError({"amount": f"Payment must be positive and at most the outstanding balance {balance:.2f}."})
    payment = FolioPayment.objects.create(
        tenant_id=folio.tenant_id,
        folio=folio,
        amount=amount,
        method=method,
        reference=(reference or "")[:128],
        idempotency_key=idempotency_key,
        recorded_by=user,
    )
    from apps.finance.services import post_folio_payment_income

    post_folio_payment_income(payment=payment, user=user)
    log_audit(
        tenant_id=folio.tenant_id,
        user_id=user.id if user else None,
        action="lodging.folio_payment",
        entity_type="folio_payment",
        entity_id=str(payment.id),
        payload={"folio_id": str(folio.id), "amount": str(payment.amount), "method": payment.method},
    )
    return payment


@transaction.atomic
def close_folio(*, folio: Folio, user) -> Folio:
    folio = Folio.objects.select_for_update().get(pk=folio.pk)
    if folio.status == FolioStatus.CLOSED:
        return folio
    _charges, _paid, balance = folio_totals(folio)
    if balance != 0:
        raise ValidationError({"detail": f"Folio must be fully settled before closing. Outstanding balance: {balance:.2f}."})
    folio.status = FolioStatus.CLOSED
    folio.save(update_fields=["status", "updated_at"])
    log_audit(
        tenant_id=folio.tenant_id,
        user_id=user.id if user else None,
        action="lodging.folio_closed",
        entity_type="folio",
        entity_id=str(folio.id),
        payload={"guest_name": folio.guest_name},
    )
    return folio


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

    room = Room.objects.select_for_update().get(pk=reservation.room_id)
    if not room.is_active:
        raise ValidationError({"room": "This room is inactive and cannot be checked in."})
    if room.status not in (RoomStatus.CLEAN, RoomStatus.INSPECTED):
        raise ValidationError({"room": "Room must be clean or inspected before check-in."})

    validate_room_available_for_reservation(reservation=reservation, room=room)

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

    open_folios = Folio.objects.select_for_update().filter(reservation=reservation, status=FolioStatus.OPEN)
    for folio in open_folios:
        _charges, _paid, balance = folio_totals(folio)
        if balance != 0:
            raise ValidationError({"detail": f"Settle the guest folio before checkout. Outstanding balance: {balance:.2f}."})
        close_folio(folio=folio, user=user)

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
