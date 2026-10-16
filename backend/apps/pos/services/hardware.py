"""Workstation device capability boundary and operator-observed test evidence.

No printer, scanner, drawer or scale is driven directly from the Django
server. A configured label must never be mistaken for physical availability.
"""
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.pos.models import Workstation, WorkstationHardwareCheck
from apps.tenants.models import Tenant
from apps.staff.services.membership import staff_accessible_outlets
from apps.staff.services.modules import get_tenant_staff_modules

ADMIN_ROLES = {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}
DEVICE_TYPES = {
    "receipt_printer": "receipt_printer",
    "barcode_scanner": None,
    "kitchen_display": "kitchen_printer",
    "cash_drawer": "cash_drawer",
    "weighing_scale": None,
}
RESULTS = {"pass", "fail", "not_tested"}


def browser_device_capabilities(station):
    """Display a truthful adapter availability summary.

    These browser fallbacks are separate from unattended hardware control.
    """
    return {
        "receipt_print": {
            "available": True, "method": "browser_print_dialog",
            "direct_output": False,
        },
        "barcode_input": {
            "available": True, "method": "keyboard_wedge_input",
            "direct_output": False,
        },
        "kitchen_print": {
            "available": False, "method": "requires_approved_adapter",
            "direct_output": False,
        },
        "drawer_open": {
            "available": False, "method": "requires_approved_adapter",
            "direct_output": False,
        },
        "scale_read": {
            "available": False, "method": "requires_approved_adapter",
            "direct_output": False,
        },
    }


@transaction.atomic
def record_hardware_check(*, tenant, workstation_id, membership, user,
                          test_type, result, note=""):
    if (
        membership is None or not membership.is_active
        or membership.tenant_id != tenant.pk or membership.user_id != user.pk
        or membership.role not in ADMIN_ROLES
    ):
        raise ValidationError({"detail": "Only a workspace owner or administrator can record equipment checks."})
    station = Workstation.objects.select_for_update().select_related("outlet").filter(
        pk=workstation_id, tenant=tenant, outlet__site__tenant=tenant,
    ).first()
    if station is None or station.outlet_id not in {
        o.pk for o in staff_accessible_outlets(membership)
    }:
        raise ValidationError({"workstation": "This workstation is not assigned to your workspace."})
    if test_type not in DEVICE_TYPES or result not in RESULTS:
        raise ValidationError({"result": "Choose an equipment type and test outcome."})
    # Resolve a fresh business configuration: a previously accessed tenant.settings
    # relation can be stale after an administrator disables a business line.
    if test_type == "kitchen_display" and "kitchen" not in get_tenant_staff_modules(
        Tenant.objects.get(pk=tenant.pk), outlet=station.outlet,
    ):
        raise ValidationError({"test_type": "Kitchen hardware is not enabled for this section."})
    note = (note or "").strip()
    if len(note) > 500:
        raise ValidationError({"note": "Use a note of up to 500 characters."})
    if result == "fail" and not note:
        raise ValidationError({"note": "Describe the observed problem before saving a failure."})
    label_field = DEVICE_TYPES[test_type]
    observed_label = (getattr(station, label_field, "") if label_field else "") or ""
    recorded = WorkstationHardwareCheck.objects.create(
        tenant=tenant, workstation=station, checked_by=user,
        test_type=test_type, result=result, note=note,
        configured_device=observed_label[:120],
    )
    log_audit(
        tenant_id=tenant.pk, user_id=user.pk,
        action="workstation.hardware_check_recorded",
        entity_type="hardware_check", entity_id=str(recorded.pk),
        payload={
            "outlet_id": str(station.outlet_id),
            "workstation_id": str(station.pk),
            "type": test_type, "result": result,
        },
    )
    return recorded
