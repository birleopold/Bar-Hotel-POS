from __future__ import annotations

from datetime import timedelta
import hashlib
import json

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Membership
from apps.audit.models import SensitiveActionApproval
from apps.audit.services import log_audit

from .membership import staff_outlet_allowed_for_membership
from .permissions import (
    SENSITIVE_APPROVAL_ROLES,
    membership_can_approve_sensitive_action,
)


APPROVAL_TTL = timedelta(minutes=2)


class SensitiveApprovalError(ValueError):
    pass


def sensitive_action_approvers(*, requester: Membership, action: str, outlet_id) -> list[Membership]:
    """Return PIN-enabled eligible approvers scoped to this tenant/outlet."""
    if action not in {
        "refund", "retail_line_refund", "discount", "void",
        "reopen", "stock_write_off", "price_override", "withdrawal",
    }:
        return []
    candidates = list(
        Membership.objects.filter(
            tenant_id=requester.tenant_id,
            is_active=True,
            role__in=SENSITIVE_APPROVAL_ROLES,
            user__is_active=True,
        )
        .exclude(pk=requester.pk)
        .exclude(staff_pin_hash="")
        .select_related("user", "tenant")
        .order_by("user__email")
    )
    if outlet_id:
        candidates = [
            member for member in candidates
            if staff_outlet_allowed_for_membership(member, outlet_id)
        ]
    return candidates


def approval_intent_hash(
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    intent_payload: dict,
) -> str:
    canonical = json.dumps(
        {
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "intent": intent_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@transaction.atomic
def authorize_sensitive_action(
    *,
    requester: Membership,
    approver_id,
    approver_pin: str,
    action: str,
    entity_type: str,
    entity_id: str,
    request_key: str,
    intent_payload: dict,
    outlet_id=None,
) -> SensitiveActionApproval:
    """Verify manager PIN and consume one exact approval.

    Exact idempotent retries return the already-consumed approval. A reused
    request key with changed intent is rejected.
    """
    from apps.staff.terminal import verify_member_pin

    request_key = str(request_key or "").strip()
    if not request_key:
        raise SensitiveApprovalError("Approval request identity is missing.")
    if not requester or not requester.is_active:
        raise SensitiveApprovalError("The requesting staff account is not active.")

    intent_hash = approval_intent_hash(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        intent_payload=intent_payload,
    )
    existing = SensitiveActionApproval.objects.select_for_update().filter(
        tenant_id=requester.tenant_id,
        action=action,
        request_key=request_key,
    ).first()
    if existing is not None:
        if (
            existing.entity_type != entity_type
            or existing.entity_id != str(entity_id)
            or existing.intent_hash != intent_hash
            or existing.requester_id != requester.pk
        ):
            raise SensitiveApprovalError(
                "This approval request identity was already used for different transaction details."
            )
        if existing.used_at is not None:
            existing.idempotent_replay = True
            return existing
        if existing.expires_at <= timezone.now():
            raise SensitiveApprovalError("Supervisor approval expired. Ask the manager to approve again.")

    approver = verify_member_pin(
        member_id=approver_id,
        tenant_id=requester.tenant_id,
        outlet_id=str(outlet_id or ""),
        pin=approver_pin or "",
    )
    if approver is None or not membership_can_approve_sensitive_action(approver, action):
        raise SensitiveApprovalError("Supervisor approval failed. Check the selected manager and PIN.")
    if approver.pk == requester.pk:
        raise SensitiveApprovalError("A different authorized manager must approve this action.")
    if outlet_id and not staff_outlet_allowed_for_membership(approver, outlet_id):
        raise SensitiveApprovalError("That manager is not authorized for this outlet.")

    now = timezone.now()
    if existing is None:
        try:
            # Keep the uniqueness race inside its own savepoint. Catching an
            # IntegrityError directly in the outer transaction would leave it
            # unusable for the idempotent lookup below.
            with transaction.atomic():
                approval = SensitiveActionApproval.objects.create(
                    tenant_id=requester.tenant_id,
                    requester=requester,
                    approver=approver,
                    scope_outlet_id=outlet_id,
                    action=action,
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    request_key=request_key,
                    intent_hash=intent_hash,
                    intent_payload=intent_payload,
                    expires_at=now + APPROVAL_TTL,
                    used_at=now,
                )
        except IntegrityError:
            approval = SensitiveActionApproval.objects.select_for_update().get(
                tenant_id=requester.tenant_id,
                action=action,
                request_key=request_key,
            )
            if (
                approval.entity_type != entity_type
                or approval.entity_id != str(entity_id)
                or approval.intent_hash != intent_hash
                or approval.requester_id != requester.pk
            ):
                raise SensitiveApprovalError(
                    "This approval request identity was already used for different transaction details."
                )
            if approval.used_at is not None:
                approval.idempotent_replay = True
                return approval
    else:
        approval = existing
        approval.approver = approver
        approval.scope_outlet_id = outlet_id
        approval.used_at = now
        approval.save(update_fields=["approver", "scope_outlet", "used_at"])

    approval.idempotent_replay = False
    log_audit(
        tenant_id=requester.tenant_id,
        user_id=approver.user_id,
        action="staff.sensitive_action_approved",
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload={
            "approval_id": str(approval.pk),
            "sensitive_action": action,
            "requester_membership_id": str(requester.pk),
            "approver_membership_id": str(approver.pk),
            "intent_hash": intent_hash,
            "outlet_id": str(outlet_id or ""),
            "expires_at": approval.expires_at.isoformat(),
        },
    )
    return approval
