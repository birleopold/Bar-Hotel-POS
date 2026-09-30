"""Register attribution shared by online, API, refund and offline settlement."""
import uuid

from rest_framework.exceptions import ValidationError

from apps.pos.models import PosShift, PosShiftStatus, Workstation
from apps.tenants.models import Outlet


def _identifier(value, field):
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({field: "Choose a valid register identifier."})


def check_replay_register(record, *, workstation_id=None, shift_id=None):
    shift_id = _identifier(shift_id, "shift_id")
    workstation_id = _identifier(workstation_id, "workstation_id")
    if ((shift_id is not None and record.shift_id != shift_id)
            or (workstation_id is not None and (record.shift_id is None or record.shift.workstation_id != workstation_id))):
        raise ValidationError({"Idempotency-Key": "This key was already used at a different register."})


def resolve_settlement_shift(*, order, workstation_id=None, shift_id=None):
    """Called inside settlement's transaction, after locking the order.

    Close/open also lock the outlet before a shift. This serializes register
    selection with shift transitions without locking every order at close.
    """
    workstation_id = _identifier(workstation_id, "workstation_id")
    shift_id = _identifier(shift_id, "shift_id")
    Outlet.objects.select_for_update().get(pk=order.outlet_id, site__tenant_id=order.tenant_id)
    qs = PosShift.objects.select_for_update().filter(tenant_id=order.tenant_id, outlet_id=order.outlet_id, status=PosShiftStatus.OPEN)
    if workstation_id is not None:
        if not Workstation.objects.filter(pk=workstation_id, tenant_id=order.tenant_id, outlet_id=order.outlet_id, is_active=True).exists():
            raise ValidationError({"workstation_id": "Choose an enabled workstation in this order's section."})
        qs = qs.filter(workstation_id=workstation_id)
    if shift_id is not None:
        qs = qs.filter(pk=shift_id)
    shifts = list(qs[:2])
    if len(shifts) > 1:
        raise ValidationError({"workstation_id": "Several tills are open. Select the till handling this transaction."})
    if not shifts:
        if workstation_id is not None or shift_id is not None:
            raise ValidationError({"shift_id": "Open this register before recording a payment or refund. Closed-shift offline actions need review."})
        return None  # Preserve existing integrations that operate without a register.
    shift = shifts[0]
    if shift.workstation_id and not Workstation.objects.filter(pk=shift.workstation_id, is_active=True, outlet_id=order.outlet_id, tenant_id=order.tenant_id).exists():
        raise ValidationError({"workstation_id": "This register's workstation is unavailable."})
    return shift
