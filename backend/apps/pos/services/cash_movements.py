from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.pos.models import CashDrawerMovement, PosShift, PosShiftStatus
from apps.tenants.models import Outlet
from apps.access.outlets import outlet_belongs_to_membership

MANAGER_ROLES = {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER}
VALID_DIRECTIONS = {"float_add", "drop", "payout"}


@transaction.atomic
def record_cash_drawer_movement(*, shift, membership, user, direction, amount, reason, idempotency_key, workstation_id=None):
    if (not membership.is_active or membership.tenant_id != shift.tenant_id or membership.user_id != user.pk
            or not outlet_belongs_to_membership(membership, shift.outlet_id)):
        raise ValidationError("You cannot record cash movement for this register.")
    if direction not in VALID_DIRECTIONS or not reason or not reason.strip() or len(reason.strip()) > 255:
        raise ValidationError("Choose a movement and provide a reason of up to 255 characters.")
    if not idempotency_key or len(idempotency_key) > 128:
        raise ValidationError("A unique movement key is required.")
    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Enter a valid positive cash amount.") from None
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2 or amount >= Decimal("1000000000000"):
        raise ValidationError("Enter a positive amount with at most two decimal places.")
    Outlet.objects.select_for_update().get(pk=shift.outlet_id, site__tenant_id=shift.tenant_id)
    locked = PosShift.objects.select_for_update().get(pk=shift.pk, tenant_id=shift.tenant_id)
    if locked.workstation_id != workstation_id:
        raise ValidationError("Use the workstation assigned to this shift.")
    prior = CashDrawerMovement.objects.filter(tenant_id=locked.tenant_id, shift=locked, idempotency_key=idempotency_key).first()
    if prior:
        if prior.direction != direction or prior.amount != amount or prior.reason != reason.strip():
            raise ValidationError("This movement key already belongs to a different entry.")
        return prior, True
    if locked.status != PosShiftStatus.OPEN:
        raise ValidationError("This register shift is closed.")
    if membership.role not in MANAGER_ROLES and locked.opened_by_id != user.pk:
        raise ValidationError("Only the opening cashier or a manager may move this drawer's cash.")
    if direction == "payout" and membership.role not in MANAGER_ROLES:
        raise ValidationError("A manager must record cash payouts.")
    if direction in {"drop", "payout"}:
        from .orders import shift_cash_snapshot
        if amount > shift_cash_snapshot(shift=locked)["expected"]:
            raise ValidationError("Cash removed cannot exceed the expected cash in this drawer.")
    entry = CashDrawerMovement.objects.create(tenant_id=locked.tenant_id, shift=locked, direction=direction, amount=amount, reason=reason.strip(), idempotency_key=idempotency_key, recorded_by=user)
    log_audit(tenant_id=locked.tenant_id, user_id=user.pk, action="pos.cash_drawer_movement", entity_type="cash_drawer_movement", entity_id=str(entry.pk), payload={"shift_id": str(locked.pk), "workstation_id": str(locked.workstation_id) if locked.workstation_id else None, "direction": direction, "amount": str(amount), "reason": entry.reason})
    return entry, False
