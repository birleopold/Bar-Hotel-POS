"""Authenticated local hardware bridge provisioning and command queue."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import secrets
import uuid

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from apps.audit.services import log_audit
from apps.pos.models import (
    Workstation,
    WorkstationBridgeCredential,
    WorkstationDevice,
    WorkstationDeviceAdapter,
    WorkstationDeviceCommand,
    WorkstationDeviceCommandStatus,
    WorkstationDeviceCommandType,
    WorkstationDeviceType,
)
from .device_adapters import ADAPTER_POLICY, record_adapter_heartbeat


COMMANDS_BY_DEVICE = {
    WorkstationDeviceType.RECEIPT_PRINTER: {
        WorkstationDeviceCommandType.PING,
        WorkstationDeviceCommandType.PRINT_RECEIPT,
    },
    WorkstationDeviceType.KITCHEN_PRINTER: {
        WorkstationDeviceCommandType.PING,
        WorkstationDeviceCommandType.PRINT_KITCHEN,
    },
    WorkstationDeviceType.CASH_DRAWER: {
        WorkstationDeviceCommandType.PING,
        WorkstationDeviceCommandType.OPEN_DRAWER,
    },
    WorkstationDeviceType.WEIGHING_SCALE: {
        WorkstationDeviceCommandType.PING,
        WorkstationDeviceCommandType.READ_SCALE,
        WorkstationDeviceCommandType.TARE_SCALE,
    },
    WorkstationDeviceType.BARCODE_SCANNER: {
        WorkstationDeviceCommandType.PING,
    },
    WorkstationDeviceType.CUSTOMER_DISPLAY: {
        WorkstationDeviceCommandType.PING,
    },
}
CLAIM_TIMEOUT = timedelta(seconds=30)
DEFAULT_COMMAND_TTL = timedelta(minutes=2)


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@transaction.atomic
def provision_bridge_credential(
    *,
    tenant,
    workstation: Workstation,
    user,
    label: str,
    expires_days: int = 90,
):
    if workstation.tenant_id != tenant.pk:
        raise ValidationError({"workstation": "Choose a workstation in this workspace."})
    label = " ".join((label or "").split())
    if not label:
        raise ValidationError({"label": "Enter a bridge name."})
    if expires_days < 1 or expires_days > 365:
        raise ValidationError({"expires_days": "Choose 1 to 365 days."})
    secret = secrets.token_urlsafe(32)
    credential = WorkstationBridgeCredential.objects.create(
        tenant=tenant,
        workstation=workstation,
        label=label[:80],
        token_hash=_hash_secret(secret),
        approved_by=user,
        expires_at=timezone.now() + timedelta(days=expires_days),
    )
    log_audit(
        tenant_id=tenant.pk,
        user_id=user.pk,
        action="workstation.bridge_credential_created",
        entity_type="workstation_bridge_credential",
        entity_id=str(credential.pk),
        payload={
            "workstation_id": str(workstation.pk),
            "label": credential.label,
            "expires_at": credential.expires_at.isoformat(),
        },
        source="staff",
    )
    return credential, f"{credential.pk}.{secret}"


@transaction.atomic
def revoke_bridge_credential(*, credential, user, reason: str):
    locked = WorkstationBridgeCredential.objects.select_for_update().get(
        pk=credential.pk,
        tenant_id=credential.tenant_id,
    )
    if locked.revoked_at is not None:
        return locked
    locked.revoked_at = timezone.now()
    locked.revoked_by = user
    locked.revocation_reason = (reason or "Revoked by administrator")[:255]
    locked.save(
        update_fields=[
            "revoked_at",
            "revoked_by",
            "revocation_reason",
            "updated_at",
        ]
    )
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk,
        action="workstation.bridge_credential_revoked",
        entity_type="workstation_bridge_credential",
        entity_id=str(locked.pk),
        payload={
            "workstation_id": str(locked.workstation_id),
            "reason": locked.revocation_reason,
        },
        source="staff",
    )
    return locked


def authenticate_bridge_token(*, tenant_id, token: str):
    try:
        raw_id, secret = (token or "").split(".", 1)
        credential_id = uuid.UUID(raw_id)
    except (ValueError, TypeError, AttributeError):
        raise AuthenticationFailed("Invalid hardware bridge credential.")
    credential = (
        WorkstationBridgeCredential.objects.filter(
            pk=credential_id,
            tenant_id=tenant_id,
            workstation__tenant_id=tenant_id,
            workstation__is_active=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("workstation")
        .first()
    )
    if credential is None or not secrets.compare_digest(
        credential.token_hash,
        _hash_secret(secret),
    ):
        raise AuthenticationFailed("Invalid hardware bridge credential.")
    return credential


@transaction.atomic
def enqueue_device_command(
    *,
    tenant,
    device: WorkstationDevice,
    user,
    command_type: str,
    idempotency_key: str,
    payload=None,
    ttl_seconds: int = 120,
):
    locked = (
        WorkstationDevice.objects.select_for_update()
        .select_related("workstation")
        .get(
            pk=device.pk,
            tenant=tenant,
            workstation__tenant=tenant,
            is_active=True,
        )
    )
    if locked.adapter != WorkstationDeviceAdapter.LOCAL_BRIDGE:
        raise ValidationError(
            {"device": "Direct device commands require the local bridge adapter."}
        )
    if command_type not in COMMANDS_BY_DEVICE.get(locked.device_type, set()):
        raise ValidationError(
            {"command_type": "This command is not supported for the selected device."}
        )
    key = (idempotency_key or "").strip()
    if not key or len(key) > 128:
        raise ValidationError(
            {"idempotency_key": "Use a stable command key of up to 128 characters."}
        )
    if ttl_seconds < 10 or ttl_seconds > 600:
        raise ValidationError({"ttl_seconds": "Use a command TTL from 10 to 600 seconds."})
    existing = WorkstationDeviceCommand.objects.filter(
        tenant=tenant,
        idempotency_key=key,
    ).first()
    if existing:
        if (
            existing.device_id != locked.pk
            or existing.command_type != command_type
        ):
            raise ValidationError(
                {"idempotency_key": "This command key was already used for a different device action."}
            )
        return existing, True
    policy = ADAPTER_POLICY[locked.adapter]
    command = WorkstationDeviceCommand.objects.create(
        tenant=tenant,
        workstation=locked.workstation,
        device=locked,
        command_type=command_type,
        idempotency_key=key,
        payload=payload or {},
        max_attempts=policy.retry_attempts,
        expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
        created_by=user,
    )
    log_audit(
        tenant_id=tenant.pk,
        user_id=getattr(user, "pk", None),
        action="workstation.device_command_queued",
        entity_type="workstation_device_command",
        entity_id=str(command.pk),
        payload={
            "workstation_id": str(locked.workstation_id),
            "device_id": str(locked.pk),
            "device_type": locked.device_type,
            "command_type": command.command_type,
            "max_attempts": command.max_attempts,
        },
        source="staff",
    )
    return command, False


@transaction.atomic
def claim_bridge_commands(*, credential, limit: int = 10):
    if limit < 1 or limit > 50:
        raise ValidationError({"limit": "Claim between 1 and 50 commands."})
    now = timezone.now()
    locked_credential = WorkstationBridgeCredential.objects.select_for_update().get(
        pk=credential.pk,
        tenant_id=credential.tenant_id,
        revoked_at__isnull=True,
        expires_at__gt=now,
    )
    locked_credential.last_seen_at = now
    locked_credential.save(update_fields=["last_seen_at", "updated_at"])

    WorkstationDeviceCommand.objects.filter(
        tenant_id=credential.tenant_id,
        workstation_id=credential.workstation_id,
        status__in=[
            WorkstationDeviceCommandStatus.PENDING,
            WorkstationDeviceCommandStatus.CLAIMED,
        ],
        expires_at__lte=now,
    ).update(
        status=WorkstationDeviceCommandStatus.EXPIRED,
        finished_at=now,
        error="Command expired before completion.",
    )

    stale_before = now - CLAIM_TIMEOUT
    stale_ids = list(
        WorkstationDeviceCommand.objects.select_for_update(skip_locked=True)
        .filter(
            tenant_id=credential.tenant_id,
            workstation_id=credential.workstation_id,
            status=WorkstationDeviceCommandStatus.CLAIMED,
            claimed_at__lt=stale_before,
            expires_at__gt=now,
            attempts__lt=models.F("max_attempts"),
        )
        .values_list("pk", flat=True)
    )
    if stale_ids:
        WorkstationDeviceCommand.objects.filter(pk__in=stale_ids).update(
            status=WorkstationDeviceCommandStatus.PENDING,
            claimed_at=None,
            error="Bridge claim timed out; command returned to retry queue.",
        )

    commands = list(
        WorkstationDeviceCommand.objects.select_for_update(skip_locked=True)
        .filter(
            tenant_id=credential.tenant_id,
            workstation_id=credential.workstation_id,
            device__adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
            device__is_active=True,
            status=WorkstationDeviceCommandStatus.PENDING,
            expires_at__gt=now,
        )
        .filter(Q(not_before__isnull=True) | Q(not_before__lte=now))
        .select_related("device")
        .order_by("created_at", "pk")[:limit]
    )
    for command in commands:
        command.status = WorkstationDeviceCommandStatus.CLAIMED
        command.claimed_at = now
        command.attempts += 1
        command.save(
            update_fields=["status", "claimed_at", "attempts", "updated_at"]
        )
    return commands


@transaction.atomic
def report_bridge_command(
    *,
    credential,
    command_id,
    success: bool,
    result=None,
    error="",
    latency_ms=None,
):
    now = timezone.now()
    command = (
        WorkstationDeviceCommand.objects.select_for_update()
        .select_related("device")
        .filter(
            pk=command_id,
            tenant_id=credential.tenant_id,
            workstation_id=credential.workstation_id,
            status=WorkstationDeviceCommandStatus.CLAIMED,
        )
        .first()
    )
    if command is None:
        raise ValidationError(
            {"command": "This command is unavailable, completed, expired or not claimed by this workstation."}
        )
    if success:
        command.status = WorkstationDeviceCommandStatus.SUCCEEDED
        command.finished_at = now
        command.result = result or {}
        command.error = ""
        command.save(
            update_fields=[
                "status",
                "finished_at",
                "result",
                "error",
                "updated_at",
            ]
        )
        record_adapter_heartbeat(
            device=command.device,
            user=None,
            success=True,
            latency_ms=latency_ms,
        )
    else:
        policy = ADAPTER_POLICY[command.device.adapter]
        message = (error or "Bridge command failed.")[:500]
        final = command.attempts >= command.max_attempts or command.expires_at <= now
        if final:
            command.status = WorkstationDeviceCommandStatus.FAILED
            command.finished_at = now
            command.not_before = None
        else:
            command.status = WorkstationDeviceCommandStatus.PENDING
            delay_index = min(
                max(command.attempts - 1, 0),
                max(len(policy.retry_backoff_ms) - 1, 0),
            )
            delay_ms = (
                policy.retry_backoff_ms[delay_index]
                if policy.retry_backoff_ms else 0
            )
            command.not_before = now + timedelta(milliseconds=delay_ms)
            command.claimed_at = None
        command.error = message
        command.save(
            update_fields=[
                "status",
                "finished_at",
                "not_before",
                "claimed_at",
                "error",
                "updated_at",
            ]
        )
        record_adapter_heartbeat(
            device=command.device,
            user=None,
            success=False,
            latency_ms=latency_ms,
            error=message,
        )
    return command


def queue_cash_drawer_for_payment_best_effort(*, payment_id):
    """Queue drawer opening after a committed cash payment without risking the sale.

    Hardware failure must never roll back or duplicate a financial transaction.
    """
    from apps.pos.models import Payment
    try:
        payment = (
            Payment.objects.select_related(
                "shift",
                "shift__workstation",
                "order",
            )
            .get(pk=payment_id)
        )
    except Payment.DoesNotExist:
        return []
    if payment.method != "cash" or not payment.shift_id or not payment.shift.workstation_id:
        return []
    devices = list(
        WorkstationDevice.objects.filter(
            tenant_id=payment.tenant_id,
            workstation_id=payment.shift.workstation_id,
            device_type=WorkstationDeviceType.CASH_DRAWER,
            adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
            is_active=True,
        )
    )
    queued = []
    for device in devices:
        try:
            command, _replay = enqueue_device_command(
                tenant=payment.order.tenant,
                device=device,
                user=payment.recorded_by,
                command_type=WorkstationDeviceCommandType.OPEN_DRAWER,
                idempotency_key=f"cash-payment:{payment.pk}:drawer:{device.pk}",
                payload={
                    "payment_id": str(payment.pk),
                    "order_id": str(payment.order_id),
                    "reason": "cash_payment_recorded",
                },
                ttl_seconds=90,
            )
            queued.append(command)
        except Exception as exc:
            log_audit(
                tenant_id=payment.tenant_id,
                user_id=payment.recorded_by_id,
                action="workstation.drawer_command_queue_failed",
                entity_type="payment",
                entity_id=str(payment.pk),
                payload={
                    "device_id": str(device.pk),
                    "error": str(exc)[:300],
                },
                source="pos",
            )
    return queued
