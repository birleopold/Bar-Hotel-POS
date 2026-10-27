"""Hardware adapter policy, health summaries and bounded retry semantics.

The Django server is the control/configuration plane. It does not directly
open USB/Bluetooth devices. Browser capabilities and future local bridges must
report only what they can truthfully observe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.pos.models import (
    WorkstationDevice,
    WorkstationDeviceAdapter,
    WorkstationDeviceHealth,
    WorkstationDeviceType,
    WorkstationHardwareCheck,
)


@dataclass(frozen=True)
class AdapterPolicy:
    automatic_control: bool
    live_health: bool
    retry_attempts: int
    retry_backoff_ms: tuple[int, ...]
    explanation: str


ADAPTER_POLICY = {
    WorkstationDeviceAdapter.BROWSER_PRINT: AdapterPolicy(
        automatic_control=False,
        live_health=False,
        retry_attempts=1,
        retry_backoff_ms=(),
        explanation=(
            "Uses the browser print dialog. The browser can open printing, "
            "but cannot certify which physical printer completed the job."
        ),
    ),
    WorkstationDeviceAdapter.KEYBOARD_WEDGE: AdapterPolicy(
        automatic_control=False,
        live_health=False,
        retry_attempts=1,
        retry_backoff_ms=(),
        explanation=(
            "Scanner behaves like keyboard input. Successful characters prove "
            "input reached the browser, not that a specific scanner is online."
        ),
    ),
    WorkstationDeviceAdapter.PAIRED_BROWSER: AdapterPolicy(
        automatic_control=False,
        live_health=True,
        retry_attempts=3,
        retry_backoff_ms=(250, 750),
        explanation=(
            "Uses an approved browser/session, suitable for the existing "
            "customer-facing display. Browser presence can be monitored."
        ),
    ),
    WorkstationDeviceAdapter.LOCAL_BRIDGE: AdapterPolicy(
        automatic_control=True,
        live_health=True,
        retry_attempts=3,
        retry_backoff_ms=(250, 750),
        explanation=(
            "Reserved for an installed local hardware bridge. Commands and "
            "telemetry must be authenticated by that bridge before use."
        ),
    ),
    WorkstationDeviceAdapter.MANUAL: AdapterPolicy(
        automatic_control=False,
        live_health=False,
        retry_attempts=1,
        retry_backoff_ms=(),
        explanation="External/manual hardware with no automatic POS control.",
    ),
}


ALLOWED_ADAPTERS = {
    WorkstationDeviceType.RECEIPT_PRINTER: {
        WorkstationDeviceAdapter.BROWSER_PRINT,
        WorkstationDeviceAdapter.LOCAL_BRIDGE,
        WorkstationDeviceAdapter.MANUAL,
    },
    WorkstationDeviceType.KITCHEN_PRINTER: {
        WorkstationDeviceAdapter.LOCAL_BRIDGE,
        WorkstationDeviceAdapter.MANUAL,
    },
    WorkstationDeviceType.CASH_DRAWER: {
        WorkstationDeviceAdapter.LOCAL_BRIDGE,
        WorkstationDeviceAdapter.MANUAL,
    },
    WorkstationDeviceType.BARCODE_SCANNER: {
        WorkstationDeviceAdapter.KEYBOARD_WEDGE,
        WorkstationDeviceAdapter.LOCAL_BRIDGE,
        WorkstationDeviceAdapter.MANUAL,
    },
    WorkstationDeviceType.WEIGHING_SCALE: {
        WorkstationDeviceAdapter.LOCAL_BRIDGE,
        WorkstationDeviceAdapter.MANUAL,
    },
    WorkstationDeviceType.CUSTOMER_DISPLAY: {
        WorkstationDeviceAdapter.PAIRED_BROWSER,
        WorkstationDeviceAdapter.LOCAL_BRIDGE,
        WorkstationDeviceAdapter.MANUAL,
    },
}


def validate_device_adapter(*, device_type: str, adapter: str) -> None:
    allowed = ALLOWED_ADAPTERS.get(device_type, set())
    if adapter not in allowed:
        raise ValidationError(
            {
                "adapter": (
                    "This adapter cannot safely control or represent the selected "
                    "device type."
                )
            }
        )


def device_adapter_manifest(device: WorkstationDevice) -> dict:
    policy = ADAPTER_POLICY[device.adapter]
    return {
        "device_id": str(device.pk),
        "device_type": device.device_type,
        "device_type_label": device.get_device_type_display(),
        "adapter": device.adapter,
        "adapter_label": device.get_adapter_display(),
        "automatic_control": policy.automatic_control,
        "live_health": policy.live_health,
        "retry_attempts": policy.retry_attempts,
        "retry_backoff_ms": list(policy.retry_backoff_ms),
        "explanation": policy.explanation,
    }


def latest_observed_check(device: WorkstationDevice):
    legacy_type = {
        WorkstationDeviceType.RECEIPT_PRINTER: "receipt_printer",
        WorkstationDeviceType.KITCHEN_PRINTER: "kitchen_display",
        WorkstationDeviceType.CASH_DRAWER: "cash_drawer",
        WorkstationDeviceType.BARCODE_SCANNER: "barcode_scanner",
        WorkstationDeviceType.WEIGHING_SCALE: "weighing_scale",
    }.get(device.device_type)
    if not legacy_type:
        return None
    return (
        WorkstationHardwareCheck.objects.filter(
            tenant_id=device.tenant_id,
            workstation_id=device.workstation_id,
            test_type=legacy_type,
        )
        .select_related("checked_by")
        .order_by("-created_at")
        .first()
    )


def device_status_summary(device: WorkstationDevice, *, now=None) -> dict:
    """Return a truthful status without converting configuration into telemetry."""
    now = now or timezone.now()
    policy = ADAPTER_POLICY[device.adapter]
    observed = latest_observed_check(device)

    health = device.health_status
    status_label = device.get_health_status_display()
    detail = ""

    if device.adapter in {
        WorkstationDeviceAdapter.BROWSER_PRINT,
        WorkstationDeviceAdapter.KEYBOARD_WEDGE,
    }:
        # These browser modes cannot prove physical connectivity. Staff
        # observation is the strongest evidence available.
        health = WorkstationDeviceHealth.UNKNOWN
        status_label = "Browser capability"
        detail = policy.explanation
        if observed and observed.result == "pass":
            status_label = "Observed working"
            detail = f"Last observed {observed.created_at:%Y-%m-%d %H:%M}."
        elif observed and observed.result == "fail":
            health = WorkstationDeviceHealth.DEGRADED
            status_label = "Observed problem"
            detail = observed.note or "A staff member observed a problem."
    elif device.adapter == WorkstationDeviceAdapter.MANUAL:
        health = WorkstationDeviceHealth.UNKNOWN
        status_label = "Manual check"
        detail = (
            observed.note if observed and observed.note
            else "No automatic health telemetry is available."
        )
    elif policy.live_health:
        if device.last_seen_at is None:
            health = WorkstationDeviceHealth.UNKNOWN
            status_label = "No live telemetry"
            detail = "No authenticated adapter heartbeat has been recorded."
        else:
            age = now - device.last_seen_at
            if age > timedelta(minutes=5):
                health = WorkstationDeviceHealth.OFFLINE
                status_label = "Offline"
                detail = "No adapter heartbeat in the last 5 minutes."
            elif device.consecutive_failures:
                health = WorkstationDeviceHealth.DEGRADED
                status_label = "Degraded"
                detail = device.last_error or "Recent adapter failures recorded."
            else:
                health = WorkstationDeviceHealth.ONLINE
                status_label = "Online"
                detail = "Authenticated adapter heartbeat is recent."

    return {
        **device_adapter_manifest(device),
        "label": device.label,
        "is_active": device.is_active,
        "health": health,
        "status_label": status_label,
        "detail": detail,
        "last_seen_at": device.last_seen_at,
        "last_success_at": device.last_success_at,
        "last_error_at": device.last_error_at,
        "last_error": device.last_error,
        "consecutive_failures": device.consecutive_failures,
        "last_latency_ms": device.last_latency_ms,
        "observed_check": observed,
    }


@transaction.atomic
def record_adapter_heartbeat(
    *,
    device: WorkstationDevice,
    user,
    success: bool,
    latency_ms: int | None = None,
    error: str = "",
):
    """Record health from an authenticated live-health adapter.

    This service intentionally does not authenticate a local bridge itself.
    Callers must already prove workstation/adapter identity before invoking it.
    """
    locked = (
        WorkstationDevice.objects.select_for_update()
        .select_related("workstation")
        .get(pk=device.pk, tenant_id=device.tenant_id)
    )
    policy = ADAPTER_POLICY[locked.adapter]
    if not policy.live_health:
        raise ValidationError(
            {"device": "This adapter does not provide trustworthy live health telemetry."}
        )
    now = timezone.now()
    locked.last_seen_at = now
    if latency_ms is not None:
        if latency_ms < 0 or latency_ms > 120000:
            raise ValidationError({"latency_ms": "Use a latency from 0 to 120000 ms."})
        locked.last_latency_ms = latency_ms
    if success:
        locked.health_status = WorkstationDeviceHealth.ONLINE
        locked.last_success_at = now
        locked.consecutive_failures = 0
        locked.last_error = ""
    else:
        locked.consecutive_failures = min(65535, locked.consecutive_failures + 1)
        locked.last_error_at = now
        locked.last_error = (error or "Adapter operation failed.")[:500]
        locked.health_status = (
            WorkstationDeviceHealth.OFFLINE
            if locked.consecutive_failures >= policy.retry_attempts
            else WorkstationDeviceHealth.DEGRADED
        )
    locked.save(
        update_fields=[
            "health_status",
            "last_seen_at",
            "last_success_at",
            "last_error_at",
            "last_error",
            "consecutive_failures",
            "last_latency_ms",
            "updated_at",
        ]
    )
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=getattr(user, "pk", None),
        action="workstation.device_health_recorded",
        entity_type="workstation_device",
        entity_id=str(locked.pk),
        payload={
            "workstation_id": str(locked.workstation_id),
            "device_type": locked.device_type,
            "adapter": locked.adapter,
            "success": success,
            "latency_ms": locked.last_latency_ms,
            "consecutive_failures": locked.consecutive_failures,
        },
        source="staff",
    )
    return locked
