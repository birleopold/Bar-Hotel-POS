"""Sequential, scoped register handover. Each transition locks its outlet first."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.pos.models import PosShift, PosShiftStatus, ShiftHandover
from apps.tenants.models import Outlet

from .orders import close_pos_shift, open_pos_shift, shift_cash_snapshot

MANAGERS = {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER}
OPERATORS = MANAGERS | {MembershipRole.SERVER, MembershipRole.BARTENDER}


def _amount(value):
    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ValidationError("Enter a valid cash amount.") from None
    if not amount.is_finite() or amount < 0 or amount >= Decimal("1000000000000") or amount.as_tuple().exponent < -2:
        raise ValidationError("Enter a nonnegative cash amount with at most two decimal places.")
    return amount.quantize(Decimal("0.01"))


def _scope(shift, membership, user):
    if (not membership.is_active or membership.user_id != user.pk or membership.tenant_id != shift.tenant_id
            or membership.role not in OPERATORS or not outlet_belongs_to_membership(membership, shift.outlet_id)):
        raise ValidationError("You cannot manage this register handover.")
    outlet = Outlet.objects.select_for_update().filter(pk=shift.outlet_id, site__tenant_id=shift.tenant_id).first()
    if outlet is None:
        raise ValidationError("Register outlet not found.")
    locked = PosShift.objects.select_for_update().get(pk=shift.pk, tenant_id=shift.tenant_id)
    return locked


def _audit(handover, user, action, **details):
    log_audit(tenant_id=handover.tenant_id, user_id=user.pk, action=action,
              entity_type="shift_handover", entity_id=str(handover.pk),
              payload={"shift_id": str(handover.shift_id), **details})


@transaction.atomic
def submit_shift_handover(*, shift, membership, user, counted_cash, explanation="", workstation_id=None):
    locked = _scope(shift, membership, user)
    if locked.workstation_id != workstation_id or locked.status != PosShiftStatus.OPEN:
        raise ValidationError("Choose the open shift at this register.")
    if locked.opened_by_id != user.pk and membership.role not in MANAGERS:
        raise ValidationError("Only the opening cashier or a manager can submit this drawer.")
    counted = _amount(counted_cash)
    explanation = explanation.strip()
    if len(explanation) > 512 or (counted != shift_cash_snapshot(shift=locked)["expected"] and not explanation):
        raise ValidationError("Explain the cash difference (up to 512 characters).")
    close_pos_shift(shift=locked, user=user, counted_cash=counted, note=explanation[:255])
    handover = ShiftHandover.objects.create(tenant_id=locked.tenant_id, shift=locked, variance_explanation=explanation)
    _audit(handover, user, "pos.handover_submitted", counted_cash=str(counted), expected_cash=str(locked.expected_cash), explanation=explanation)
    return handover


@transaction.atomic
def verify_shift_handover(*, handover, membership, user, counted_cash, note=""):
    shift = _scope(handover.shift, membership, user)
    locked = ShiftHandover.objects.select_for_update().get(pk=handover.pk, tenant_id=shift.tenant_id, shift=shift)
    if locked.status != ShiftHandover.Status.SUBMITTED or shift.closed_by_id == user.pk:
        raise ValidationError("An independent worker must count this submitted drawer.")
    counted = _amount(counted_cash)
    note = note.strip()
    if len(note) > 512 or (counted != shift.counted_cash and not note):
        raise ValidationError("Explain any difference from the submitted count (up to 512 characters).")
    locked.status = ShiftHandover.Status.VERIFIED
    locked.verified_cash, locked.verification_note = counted, note
    locked.verified_by, locked.verified_at = user, timezone.now()
    locked.save(update_fields=["status", "verified_cash", "verification_note", "verified_by", "verified_at", "updated_at"])
    _audit(locked, user, "pos.handover_verified", verified_cash=str(counted), note=note)
    return locked


@transaction.atomic
def approve_shift_handover(*, handover, membership, user, note=""):
    shift = _scope(handover.shift, membership, user)
    locked = ShiftHandover.objects.select_for_update().get(pk=handover.pk, tenant_id=shift.tenant_id, shift=shift)
    if membership.role not in MANAGERS or locked.status != ShiftHandover.Status.VERIFIED or user.pk in {shift.closed_by_id, locked.verified_by_id}:
        raise ValidationError("A separate manager must approve the verified drawer.")
    note = note.strip()
    if len(note) > 512 or (locked.verified_cash != shift.expected_cash and not note):
        raise ValidationError("Explain approval of a cash variance (up to 512 characters).")
    locked.status = ShiftHandover.Status.APPROVED
    locked.approved_by, locked.approved_at, locked.approval_note = user, timezone.now(), note
    locked.save(update_fields=["status", "approved_by", "approved_at", "approval_note", "updated_at"])
    _audit(locked, user, "pos.handover_approved", approved_cash=str(locked.verified_cash), note=note)
    return locked


@transaction.atomic
def accept_shift_handover(*, handover, membership, user, opening_cash, workstation_id=None):
    shift = _scope(handover.shift, membership, user)
    locked = ShiftHandover.objects.select_for_update().get(pk=handover.pk, tenant_id=shift.tenant_id, shift=shift)
    amount = _amount(opening_cash)
    if locked.status != ShiftHandover.Status.APPROVED or locked.shift.workstation_id != workstation_id:
        raise ValidationError("Choose this register's approved handover.")
    if user.pk in {shift.closed_by_id, locked.approved_by_id}:
        raise ValidationError("A different cashier must accept the approved handover.")
    if amount != locked.verified_cash:
        raise ValidationError("Opening cash must equal the independently verified carried float.")
    next_shift = open_pos_shift(tenant_id=shift.tenant_id, outlet=shift.outlet, user=user, opening_cash=amount, workstation=shift.workstation, handover_id=locked.pk)
    locked.status = ShiftHandover.Status.ACCEPTED
    locked.accepted_by, locked.accepted_at, locked.next_shift = user, timezone.now(), next_shift
    locked.save(update_fields=["status", "accepted_by", "accepted_at", "next_shift", "updated_at"])
    _audit(locked, user, "pos.handover_accepted", next_shift_id=str(next_shift.pk), opening_cash=str(amount))
    return locked
