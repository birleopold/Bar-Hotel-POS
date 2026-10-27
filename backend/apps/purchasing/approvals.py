"""Approval workflow for draft purchase requests.

A pending draft PO is the request. Approval does not send anything to a
supplier; it only authorizes the existing draft to move to the normal send /
receive lifecycle.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit

from .models import PurchaseApprovalStatus, PurchaseOrder, PurchaseOrderStatus


APPROVER_ROLES = frozenset({
    MembershipRole.OWNER,
    MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER,
    MembershipRole.OUTLET_MANAGER,
})


@transaction.atomic
def review_purchase_order_request(
    *,
    po: PurchaseOrder,
    membership,
    user,
    decision: str,
    note: str = "",
) -> PurchaseOrder:
    locked = (
        PurchaseOrder.objects.select_for_update()
        .select_related("outlet", "outlet__site", "supplier", "created_by")
        .get(pk=po.pk)
    )
    if (
        membership is None
        or not membership.is_active
        or membership.tenant_id != locked.tenant_id
        or membership.user_id != user.pk
        or membership.role not in APPROVER_ROLES
        or not outlet_belongs_to_membership(membership, locked.outlet_id)
    ):
        raise ValidationError({"approval": "You are not authorized to review this purchase request."})
    if locked.status != PurchaseOrderStatus.DRAFT:
        raise ValidationError({"approval": "Only draft purchase requests can be reviewed."})
    if locked.approval_status != PurchaseApprovalStatus.PENDING:
        raise ValidationError({"approval": "This purchase request has already been reviewed."})
    if locked.created_by_id == user.pk:
        raise ValidationError({
            "approval": "A different manager must review a purchase request they did not create."
        })
    decision = (decision or "").strip().lower()
    if decision not in {
        PurchaseApprovalStatus.APPROVED,
        PurchaseApprovalStatus.REJECTED,
    }:
        raise ValidationError({"approval": "Choose approve or reject."})
    review_note = (note or "").strip()
    if decision == PurchaseApprovalStatus.REJECTED and len(review_note) < 5:
        raise ValidationError({
            "review_note": "Explain the rejection in at least 5 characters."
        })

    locked.approval_status = decision
    locked.reviewed_by = user
    locked.reviewed_at = timezone.now()
    locked.review_note = review_note[:512]
    locked.save(update_fields=[
        "approval_status", "reviewed_by", "reviewed_at", "review_note", "updated_at",
    ])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk,
        action=(
            "purchasing.request_approved"
            if decision == PurchaseApprovalStatus.APPROVED
            else "purchasing.request_rejected"
        ),
        entity_type="purchase_order",
        entity_id=str(locked.pk),
        payload={
            "supplier_id": str(locked.supplier_id),
            "outlet_id": str(locked.outlet_id),
            "requester_id": str(locked.created_by_id or ""),
            "needed_by": str(locked.needed_by or ""),
            "request_reason": locked.request_reason,
            "review_note": locked.review_note,
        },
    )
    return locked


@transaction.atomic
def withdraw_purchase_order_request(*, po: PurchaseOrder, membership, user) -> PurchaseOrder:
    locked = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    if (
        membership is None
        or not membership.is_active
        or membership.tenant_id != locked.tenant_id
        or membership.user_id != user.pk
        or locked.created_by_id != user.pk
        or not outlet_belongs_to_membership(membership, locked.outlet_id)
    ):
        raise ValidationError({"approval": "Only the requester may withdraw this purchase request."})
    if (
        locked.status != PurchaseOrderStatus.DRAFT
        or locked.approval_status != PurchaseApprovalStatus.PENDING
    ):
        raise ValidationError({"approval": "Only a pending draft request can be withdrawn."})
    locked.status = PurchaseOrderStatus.CANCELLED
    locked.review_note = "Withdrawn by requester"
    locked.reviewed_by = user
    locked.reviewed_at = timezone.now()
    locked.save(update_fields=[
        "status", "review_note", "reviewed_by", "reviewed_at", "updated_at",
    ])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk,
        action="purchasing.request_withdrawn",
        entity_type="purchase_order",
        entity_id=str(locked.pk),
        payload={"outlet_id": str(locked.outlet_id)},
    )
    return locked
