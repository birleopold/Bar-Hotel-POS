"""Stock transfer request workflow layered above the existing staged transfer ledger."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.audit.services import log_audit
from apps.inventory.models import (
    StockBalance,
    StockTransferReceipt,
    StockTransferRequest,
    StockTransferRequestStatus,
)
from apps.staff.services.permissions import membership_has_inventory_capability


def _transfer_quantity(value) -> Decimal:
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"quantity": "Enter a valid transfer quantity."}) from exc
    if (
        not qty.is_finite()
        or qty <= 0
        or qty > Decimal("99999999999.999")
        or qty != qty.quantize(Decimal("0.001"))
    ):
        raise ValidationError({
            "quantity": "Transfer quantity must be positive with up to three decimal places."
        })
    return qty


@transaction.atomic
def create_stock_transfer_request(
    *,
    tenant_id,
    membership,
    from_outlet,
    to_outlet,
    menu_item,
    quantity,
    user,
    needed_by=None,
    note: str = "",
) -> StockTransferRequest:
    if not membership_has_inventory_capability(membership, "request_transfer"):
        raise ValidationError({"request": "Your role cannot request stock transfers."})
    if membership.tenant_id != tenant_id:
        raise ValidationError({"request": "Invalid business scope."})
    if from_outlet.site.tenant_id != tenant_id or to_outlet.site.tenant_id != tenant_id:
        raise ValidationError({"request": "Both sections must belong to this business."})
    if from_outlet.pk == to_outlet.pk:
        raise ValidationError({"request": "Source and destination sections must differ."})
    # The requester must control the receiving side. They may request stock from
    # another branch they cannot operate directly.
    if not outlet_belongs_to_membership(membership, to_outlet.pk):
        raise ValidationError({
            "to_outlet": "You can only request stock for a section you are authorized to operate."
        })
    if menu_item.tenant_id != tenant_id or not menu_item.track_inventory:
        raise ValidationError({"menu_item": "Choose a tracked product in this business."})
    if menu_item.serial_tracking:
        raise ValidationError({
            "menu_item": "Serial / IMEI products require identifier-specific transfer handling."
        })
    qty = _transfer_quantity(quantity)
    request_row = StockTransferRequest.objects.create(
        tenant_id=tenant_id,
        from_outlet=from_outlet,
        to_outlet=to_outlet,
        menu_item=menu_item,
        requested_quantity=qty,
        needed_by=needed_by,
        request_note=(note or "").strip()[:512],
        requested_by=user,
        status=StockTransferRequestStatus.PENDING,
    )
    log_audit(
        tenant_id=tenant_id,
        user_id=user.pk if user else None,
        action="stock.transfer_request_created",
        entity_type="stock_transfer_request",
        entity_id=str(request_row.pk),
        payload={
            "from_outlet_id": str(from_outlet.pk),
            "to_outlet_id": str(to_outlet.pk),
            "menu_item_id": str(menu_item.pk),
            "requested_quantity": str(qty),
            "needed_by": needed_by.isoformat() if needed_by else None,
        },
    )
    return request_row


@transaction.atomic
def review_stock_transfer_request(
    *,
    transfer_request: StockTransferRequest,
    membership,
    user,
    decision: str,
    approved_quantity=None,
    note: str = "",
) -> StockTransferRequest:
    locked = (
        StockTransferRequest.objects.select_for_update()
        .select_related("from_outlet", "to_outlet", "menu_item", "requested_by")
        .get(pk=transfer_request.pk)
    )
    if not membership_has_inventory_capability(membership, "approve_transfer"):
        raise ValidationError({"approval": "Only an authorized inventory manager can review this request."})
    if membership.tenant_id != locked.tenant_id:
        raise ValidationError({"approval": "Invalid business scope."})
    if not outlet_belongs_to_membership(membership, locked.from_outlet_id):
        raise ValidationError({
            "approval": "You must be authorized for the sending section to review this request."
        })
    if locked.requested_by_id == user.pk:
        raise ValidationError({"approval": "A different manager must review this transfer request."})
    if locked.status != StockTransferRequestStatus.PENDING:
        raise ValidationError({"approval": "Only pending transfer requests can be reviewed."})

    choice = (decision or "").strip().lower()
    review_note = (note or "").strip()
    if choice == StockTransferRequestStatus.REJECTED:
        if len(review_note) < 8:
            raise ValidationError({"review_note": "Explain the rejection in at least 8 characters."})
        locked.status = StockTransferRequestStatus.REJECTED
        locked.approved_quantity = None
    elif choice == StockTransferRequestStatus.APPROVED:
        qty = _transfer_quantity(
            locked.requested_quantity if approved_quantity in (None, "") else approved_quantity
        )
        if qty > locked.requested_quantity:
            raise ValidationError({
                "approved_quantity": "Approved quantity cannot exceed the requested quantity."
            })
        source = StockBalance.objects.filter(
            tenant_id=locked.tenant_id,
            outlet_id=locked.from_outlet_id,
            menu_item_id=locked.menu_item_id,
        ).only("quantity").first()
        available = source.quantity if source is not None else Decimal("0")
        if available < qty:
            raise ValidationError({
                "approved_quantity": (
                    f"Source currently has {available}; cannot approve {qty}. "
                    "Reduce the approved quantity or reconcile source stock."
                )
            })
        locked.status = StockTransferRequestStatus.APPROVED
        locked.approved_quantity = qty
    else:
        raise ValidationError({"approval": "Choose approve or reject."})

    locked.reviewed_by = user
    locked.reviewed_at = timezone.now()
    locked.review_note = review_note[:512]
    locked.save(update_fields=[
        "status", "approved_quantity", "reviewed_by", "reviewed_at",
        "review_note", "updated_at",
    ])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk if user else None,
        action=(
            "stock.transfer_request_approved"
            if locked.status == StockTransferRequestStatus.APPROVED
            else "stock.transfer_request_rejected"
        ),
        entity_type="stock_transfer_request",
        entity_id=str(locked.pk),
        payload={
            "requested_quantity": str(locked.requested_quantity),
            "approved_quantity": (
                str(locked.approved_quantity)
                if locked.approved_quantity is not None else None
            ),
            "review_note": locked.review_note,
        },
    )
    return locked


@transaction.atomic
def dispatch_stock_transfer_request(
    *,
    transfer_request: StockTransferRequest,
    membership,
    user,
) -> tuple[StockTransferRequest, StockTransferReceipt]:
    locked = (
        StockTransferRequest.objects.select_for_update()
        .select_related("from_outlet", "to_outlet", "menu_item")
        .get(pk=transfer_request.pk)
    )
    if not membership_has_inventory_capability(membership, "transfer"):
        raise ValidationError({"dispatch": "Your role cannot dispatch stock transfers."})
    if membership.tenant_id != locked.tenant_id:
        raise ValidationError({"dispatch": "Invalid business scope."})
    if not outlet_belongs_to_membership(membership, locked.from_outlet_id):
        raise ValidationError({
            "dispatch": "You must be authorized for the sending section to dispatch this request."
        })
    if locked.status == StockTransferRequestStatus.DISPATCHED and locked.transfer_receipt_id:
        return locked, locked.transfer_receipt
    if (
        locked.status != StockTransferRequestStatus.APPROVED
        or locked.approved_quantity is None
    ):
        raise ValidationError({"dispatch": "Only an approved transfer request can be dispatched."})

    from apps.inventory.services import execute_stock_transfer

    batch, _movement, _arrival = execute_stock_transfer(
        tenant_id=locked.tenant_id,
        membership=membership,
        from_outlet=locked.from_outlet,
        to_outlet=locked.to_outlet,
        menu_item=locked.menu_item,
        quantity=locked.approved_quantity,
        user=user,
        note=(
            f"Approved request {locked.pk}. {locked.request_note}"
        ).strip()[:500],
        staged=True,
        allow_destination_outside_scope=True,
    )
    receipt = StockTransferReceipt.objects.select_for_update().get(
        tenant_id=locked.tenant_id,
        transfer_batch=batch,
    )
    locked.transfer_receipt = receipt
    locked.status = StockTransferRequestStatus.DISPATCHED
    locked.save(update_fields=["transfer_receipt", "status", "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk if user else None,
        action="stock.transfer_request_dispatched",
        entity_type="stock_transfer_request",
        entity_id=str(locked.pk),
        payload={
            "transfer_batch": str(batch),
            "approved_quantity": str(locked.approved_quantity),
        },
    )
    return locked, receipt


@transaction.atomic
def cancel_stock_transfer_request(
    *,
    transfer_request: StockTransferRequest,
    membership,
    user,
) -> StockTransferRequest:
    locked = StockTransferRequest.objects.select_for_update().get(
        pk=transfer_request.pk
    )
    if membership.tenant_id != locked.tenant_id or membership.user_id != user.pk:
        raise ValidationError({"request": "Invalid request ownership."})
    if locked.requested_by_id != user.pk:
        raise ValidationError({"request": "Only the requester can cancel this transfer request."})
    if locked.status != StockTransferRequestStatus.PENDING:
        raise ValidationError({"request": "Only a pending transfer request can be cancelled."})
    if not outlet_belongs_to_membership(membership, locked.to_outlet_id):
        raise ValidationError({"request": "You no longer have access to the receiving section."})
    locked.status = StockTransferRequestStatus.CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk if user else None,
        action="stock.transfer_request_cancelled",
        entity_type="stock_transfer_request",
        entity_id=str(locked.pk),
        payload={},
    )
    return locked
