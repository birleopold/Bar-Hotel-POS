from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.finance.services import post_purchase_receive_expense_from_movement
from apps.inventory.models import StockReason
from apps.inventory.services import apply_manual_stock_change

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus


@transaction.atomic
def receive_purchase_order_goods(
    *,
    po: PurchaseOrder,
    lines_payload: list[dict],
    user,
    membership,
) -> PurchaseOrder:
    if po.status not in (
        PurchaseOrderStatus.SENT,
        PurchaseOrderStatus.PARTIALLY_RECEIVED,
    ):
        raise ValidationError(
            {"detail": "Purchase order must be sent or partially received to receive goods."}
        )
    if not outlet_belongs_to_membership(membership, po.outlet_id):
        raise ValidationError({"detail": "You cannot receive stock for this outlet."})

    po_locked = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    any_positive = False

    for row in lines_payload:
        line_id = row["line_id"]
        qty: Decimal = row["quantity"]
        if qty <= 0:
            continue
        any_positive = True
        try:
            line = PurchaseOrderLine.objects.select_for_update().get(
                purchase_order=po_locked, pk=line_id
            )
        except PurchaseOrderLine.DoesNotExist:
            raise ValidationError({"lines": f"Unknown line_id {line_id} for this purchase order."})
        remaining = line.quantity_ordered - line.quantity_received
        if qty > remaining:
            raise ValidationError(
                {
                    "lines": (
                        f"Quantity for line {line_id} exceeds remaining "
                        f"({remaining} left to receive)."
                    )
                }
            )
        movement = apply_manual_stock_change(
            tenant_id=po_locked.tenant_id,
            outlet=po_locked.outlet,
            menu_item=line.menu_item,
            quantity_change=qty,
            reason=StockReason.RECEIVE,
            user=user,
            note=(f"PO {po_locked.reference or po_locked.pk}")[:512],
            purchase_order=po_locked,
        )
        post_purchase_receive_expense_from_movement(
            movement=movement,
            po=po_locked,
            line=line,
            quantity=qty,
            user=user,
        )
        line.quantity_received += qty
        line.save(update_fields=["quantity_received", "updated_at"])

    if not any_positive:
        raise ValidationError({"lines": "At least one line must have quantity greater than zero."})

    _sync_po_status(po_locked)
    return po_locked


def _sync_po_status(po: PurchaseOrder) -> None:
    lines = list(po.lines.all())
    if not lines:
        return
    total_ord = sum(l.quantity_ordered for l in lines)
    total_rec = sum(l.quantity_received for l in lines)
    if total_rec >= total_ord:
        new_status = PurchaseOrderStatus.RECEIVED
    elif total_rec > 0:
        new_status = PurchaseOrderStatus.PARTIALLY_RECEIVED
    else:
        new_status = PurchaseOrderStatus.SENT
    if po.status != new_status:
        po.status = new_status
        po.save(update_fields=["status", "updated_at"])
