"""Approval workflow for draft purchase requests.

A pending draft PO is the request. Approval does not send anything to a
supplier; it only authorizes the existing draft to move to the normal send /
receive lifecycle.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit

from .models import (
    PurchaseApprovalStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
)


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


@transaction.atomic
def consolidate_purchase_order_requests(
    *,
    source_ids,
    membership,
    user,
    reference: str = "",
) -> PurchaseOrder:
    """Combine approved unsent requests for one supplier/outlet into one draft PO.

    Source requests remain as immutable evidence and are linked to the new
    consolidated draft. The new lines use base-stock quantities so mixed
    package requests never fabricate a package count.
    """
    ids = []
    for raw in source_ids or []:
        if raw and raw not in ids:
            ids.append(raw)
    if len(ids) < 2:
        raise ValidationError({
            "requests": "Choose at least two approved purchase requests to consolidate."
        })
    if len(ids) > 50:
        raise ValidationError({
            "requests": "Consolidate at most 50 approved requests at a time."
        })
    if (
        membership is None
        or not membership.is_active
        or membership.user_id != user.pk
        or membership.role not in APPROVER_ROLES
    ):
        raise ValidationError({
            "requests": "You are not authorized to consolidate purchase requests."
        })

    sources = list(
        PurchaseOrder.objects.select_for_update()
        .filter(pk__in=ids, tenant_id=membership.tenant_id)
        .select_related("supplier", "outlet", "created_by")
        .order_by("created_at", "pk")
    )
    if len(sources) != len(ids):
        raise ValidationError({
            "requests": "One or more selected purchase requests are outside your business."
        })

    first = sources[0]
    if not outlet_belongs_to_membership(membership, first.outlet_id):
        raise ValidationError({
            "requests": "You cannot consolidate requests for this receiving section."
        })
    for po in sources:
        if not outlet_belongs_to_membership(membership, po.outlet_id):
            raise ValidationError({
                "requests": "All selected requests must be in your authorized purchasing scope."
            })
        if po.supplier_id != first.supplier_id or po.outlet_id != first.outlet_id:
            raise ValidationError({
                "requests": "Selected requests must use the same supplier and receiving section."
            })
        if (
            po.status != PurchaseOrderStatus.DRAFT
            or po.approval_status != PurchaseApprovalStatus.APPROVED
        ):
            raise ValidationError({
                "requests": "Only approved unsent draft requests can be consolidated."
            })
        if po.consolidated_into_id:
            raise ValidationError({
                "requests": "A selected request was already consolidated."
            })
        if po.receipts.exists() or po.payments.exists() or po.invoices.exists():
            raise ValidationError({
                "requests": "A request with receipt, payment or invoice evidence cannot be consolidated."
            })

    locked_lines = list(
        PurchaseOrderLine.objects.select_for_update()
        .filter(purchase_order_id__in=[po.pk for po in sources])
        .select_related("menu_item")
        .order_by("purchase_order_id", "created_at", "pk")
    )
    source_line_map = {}
    for line in locked_lines:
        source_line_map.setdefault(line.purchase_order_id, []).append(line)

    aggregated = {}
    for po in sources:
        for line in source_line_map.get(po.pk, []):
            key = line.menu_item_id
            existing = aggregated.get(key)
            normalized_cost = (
                Decimal(line.unit_cost).quantize(Decimal("0.01"))
                if line.unit_cost is not None else None
            )
            if existing is None:
                aggregated[key] = {
                    "menu_item": line.menu_item,
                    "quantity": line.quantity_ordered,
                    "unit_cost": normalized_cost,
                    "units_per_carton_snapshot": line.units_per_carton_snapshot,
                }
                continue
            if existing["unit_cost"] != normalized_cost:
                raise ValidationError({
                    "requests": (
                        f"{line.menu_item.name} has conflicting unit costs across the "
                        "selected requests. Resolve the supplier price before consolidating."
                    )
                })
            existing["quantity"] += line.quantity_ordered
            if existing["quantity"] > Decimal("99999999999.999"):
                raise ValidationError({
                    "requests": (
                        f"Combined quantity for {line.menu_item.name} exceeds stock limits."
                    )
                })
            if existing["units_per_carton_snapshot"] != line.units_per_carton_snapshot:
                existing["units_per_carton_snapshot"] = 1

    if not aggregated:
        raise ValidationError({"requests": "Selected requests contain no order lines."})

    ref = (reference or "").strip()
    if len(ref) > 128:
        raise ValidationError({"reference": "Use a reference of up to 128 characters."})
    if not ref:
        ref = f"CONSOL-{timezone.localdate():%Y%m%d}-{str(first.pk)[:8]}"

    need_dates = [po.needed_by for po in sources if po.needed_by]
    expected_dates = [po.expected_date for po in sources if po.expected_date]
    source_labels = [po.reference or str(po.pk) for po in sources]
    target = PurchaseOrder.objects.create(
        tenant_id=membership.tenant_id,
        supplier_id=first.supplier_id,
        outlet_id=first.outlet_id,
        status=PurchaseOrderStatus.DRAFT,
        reference=ref,
        expected_date=min(expected_dates) if expected_dates else None,
        needed_by=min(need_dates) if need_dates else None,
        request_reason=f"Consolidated {len(sources)} approved purchase requests",
        notes=("Source requests: " + ", ".join(source_labels))[:4000],
        created_by=user,
        approval_status=PurchaseApprovalStatus.APPROVED,
        reviewed_by=user,
        reviewed_at=timezone.now(),
        review_note="Manager consolidated approved purchase requests",
    )
    for row in aggregated.values():
        PurchaseOrderLine.objects.create(
            purchase_order=target,
            menu_item=row["menu_item"],
            quantity_ordered=row["quantity"],
            unit_cost=row["unit_cost"],
            units_per_carton_snapshot=row["units_per_carton_snapshot"],
            product_package=None,
            package_name_snapshot="",
            package_units_snapshot=None,
            package_quantity_ordered=0,
        )

    for source in sources:
        source.consolidated_into = target
        source.status = PurchaseOrderStatus.CANCELLED
        source.save(update_fields=[
            "consolidated_into", "status", "updated_at",
        ])

    log_audit(
        tenant_id=membership.tenant_id,
        user_id=user.pk,
        action="purchasing.requests_consolidated",
        entity_type="purchase_order",
        entity_id=str(target.pk),
        payload={
            "supplier_id": str(target.supplier_id),
            "outlet_id": str(target.outlet_id),
            "source_request_ids": [str(po.pk) for po in sources],
            "source_references": source_labels,
            "line_count": len(aggregated),
            "needed_by": str(target.needed_by or ""),
            "expected_date": str(target.expected_date or ""),
        },
    )
    return target
