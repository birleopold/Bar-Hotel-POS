from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.audit.services import log_audit
from apps.finance.models import FinancePostingLink, FinancePostingSource
from apps.finance.services import post_supplier_payment_expense
from apps.inventory.models import StockMovement, StockReason
from apps.inventory.services import apply_manual_stock_change
from apps.inventory.services_batches import receive_tracked_batch
from apps.inventory.batches import InventoryBatch
from django.utils import timezone

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, PurchaseReceipt, PurchaseReceiptLine, SupplierPayment, SupplierPaymentMethod, SupplierInvoice


@transaction.atomic
def receive_purchase_order_goods(
    *,
    po: PurchaseOrder,
    lines_payload: list[dict],
    user,
    membership,
    delivery_reference: str = "",
    note: str = "",
    discrepancy_note: str = "",
) -> PurchaseOrder:
    if len(discrepancy_note) > 512:
        raise ValidationError({"discrepancy_note": "Use at most 512 characters."})
    if not outlet_belongs_to_membership(membership, po.outlet_id):
        raise ValidationError({"detail": "You cannot receive stock for this outlet."})

    po_locked = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    if delivery_reference and PurchaseReceipt.objects.filter(
        purchase_order=po_locked, delivery_reference=delivery_reference.strip()[:128]
    ).exists():
        raise ValidationError({"delivery_reference": "A delivery with this reference has already been recorded for the purchase order."})
    if po_locked.status not in (PurchaseOrderStatus.SENT, PurchaseOrderStatus.PARTIALLY_RECEIVED):
        raise ValidationError(
            {"detail": "Purchase order must be sent or partially received to receive goods."}
        )
    # Validate the complete delivery before creating a receipt or changing stock.
    # This is a server-side boundary, regardless of API/form serializers.
    if not lines_payload:
        raise ValidationError({"lines": "Enter at least one delivery line."})
    normalized = []
    for row in lines_payload:
        try:
            qty = Decimal(str(row["quantity"]))
            line_id = row["line_id"]
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValidationError({"lines": "Every delivery line needs an item and valid quantity."}) from exc
        if not qty.is_finite() or qty < 0 or qty > Decimal("99999999999.999"):
            raise ValidationError({"lines": "Delivery quantity must be finite and non-negative."})
        if qty != qty.quantize(Decimal("0.001")):
            raise ValidationError({"lines": "Delivery quantity allows at most three decimal places."})
        normalized.append({**row, "line_id": line_id, "quantity": qty})
    lines_payload = normalized
    positive_ids = [row["line_id"] for row in lines_payload if row["quantity"] > 0]
    if len(positive_ids) != len(set(positive_ids)):
        raise ValidationError({"lines": "Each purchase order line may be received only once per delivery."})
    any_positive = False
    receipt = PurchaseReceipt.objects.create(
        tenant_id=po_locked.tenant_id,
        purchase_order=po_locked,
        delivery_reference=(delivery_reference or "")[:128],
        note=(note or "")[:512],
        discrepancy_note=discrepancy_note.strip(),
        received_by=user,
    )

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
        batch_code = str(row.get("batch_code") or "").strip()
        if row.get("expiry_date") and not batch_code:
            raise ValidationError({"batch_code": "Enter a batch code when setting an expiry date."})
        if not batch_code and InventoryBatch.objects.filter(
            tenant_id=po_locked.tenant_id, outlet=po_locked.outlet,
            menu_item=line.menu_item,
        ).exists():
            raise ValidationError({"batch_code": f"Enter a batch code for {line.menu_item.name}; this product is batch-tracked."})
        batch = None
        if batch_code:
            batch, _ = receive_tracked_batch(
                tenant=po_locked.tenant,
                outlet=po_locked.outlet, menu_item=line.menu_item,
                batch_code=batch_code, quantity=qty,
                received_at=row.get("received_at") or timezone.localdate(),
                expiry_date=row.get("expiry_date"),
                user=user, purchase_order=po_locked,
            )
        else:
            apply_manual_stock_change(
                tenant_id=po_locked.tenant_id,
                outlet=po_locked.outlet,
                menu_item=line.menu_item,
                quantity_change=qty,
                reason=StockReason.RECEIVE,
                user=user,
                note=(f"PO {po_locked.reference or po_locked.pk}")[:512],
                purchase_order=po_locked,
            )
        line.quantity_received += qty
        line.save(update_fields=["quantity_received", "updated_at"])
        PurchaseReceiptLine.objects.create(
            receipt=receipt,
            purchase_order_line=line,
            quantity_received=qty,
            inventory_batch=batch,
        )

    if not any_positive:
        raise ValidationError({"lines": "At least one line must have quantity greater than zero."})

    _sync_po_status(po_locked)
    return po_locked


def received_goods_value(po: PurchaseOrder) -> Decimal:
    return sum(
        (line.quantity_received * line.unit_cost).quantize(Decimal("0.01"))
        for line in po.lines.all()
        if line.unit_cost is not None
    )


def has_legacy_receipt_expenses(po: PurchaseOrder) -> bool:
    movement_ids = [str(pk) for pk in StockMovement.objects.filter(
        purchase_order=po, reason=StockReason.RECEIVE
    ).values_list("pk", flat=True)]
    return FinancePostingLink.objects.filter(
        tenant_id=po.tenant_id, source_type=FinancePostingSource.PURCHASE_RECEIVE_MOVEMENT,
        source_id__in=movement_ids,
    ).exists()


@transaction.atomic
def confirm_missing_unit_cost(*, po: PurchaseOrder, line_id, unit_cost: Decimal, user, membership) -> PurchaseOrderLine:
    po = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    if not outlet_belongs_to_membership(membership, po.outlet_id):
        raise ValidationError({"detail": "You cannot change costs for this outlet."})
    if po.payments.exists() or has_legacy_receipt_expenses(po):
        raise ValidationError({"detail": "Costs cannot be changed after supplier settlement or legacy expense posting."})
    line = PurchaseOrderLine.objects.select_for_update().filter(purchase_order=po, pk=line_id).first()
    if line is None or line.unit_cost is not None:
        raise ValidationError({"line_id": "Select a line whose unit cost has not been confirmed."})
    if unit_cost < 0 or unit_cost != unit_cost.quantize(Decimal("0.01")):
        raise ValidationError({"unit_cost": "Enter a non-negative cost with at most two decimal places."})
    line.unit_cost = unit_cost
    line.save(update_fields=["unit_cost", "updated_at"])
    log_audit(
        tenant_id=po.tenant_id, user_id=user.id if user else None,
        action="purchase.unit_cost_confirmed", entity_type="purchase_order_line", entity_id=str(line.id),
        payload={"purchase_order_id": str(po.id), "unit_cost": str(unit_cost)},
    )
    return line


@transaction.atomic
def record_supplier_payment(
    *, po: PurchaseOrder, amount: Decimal, method: str, reference: str,
    idempotency_key: str, user, membership,
) -> tuple[SupplierPayment, bool]:
    key = (idempotency_key or "").strip()
    if not key or len(key) > 128:
        raise ValidationError({"idempotency_key": "A key of at most 128 characters is required."})
    po = PurchaseOrder.objects.select_for_update().select_related("outlet__site").get(pk=po.pk)
    if not outlet_belongs_to_membership(membership, po.outlet_id):
        raise ValidationError({"detail": "You cannot pay a supplier for this outlet."})
    reference = (reference or "").strip()
    if len(reference) > 128:
        raise ValidationError({"reference": "Must be at most 128 characters."})
    existing = SupplierPayment.objects.filter(tenant_id=po.tenant_id, idempotency_key=key).first()
    if existing:
        if (existing.purchase_order_id, existing.amount, existing.method, existing.reference) != (
            po.id, amount, method, reference
        ):
            raise ValidationError({"idempotency_key": "This key was used for a different supplier payment."})
        return existing, True
    if method not in SupplierPaymentMethod.values:
        raise ValidationError({"method": "Select a valid payment method."})
    if amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise ValidationError({"amount": "Enter a positive amount with at most two decimal places."})
    received_lines = po.lines.filter(quantity_received__gt=0)
    if not received_lines.exists() or received_lines.filter(unit_cost__isnull=True).exists():
        raise ValidationError({"detail": "Received goods need a unit cost before supplier payment can be recorded."})
    # Older releases wrote an expense on receipt. Never post the same outflow twice.
    if has_legacy_receipt_expenses(po):
        raise ValidationError({"detail": "This order has legacy receipt expenses. Reconcile those entries before recording supplier payments."})
    received_total = received_goods_value(po)
    paid = po.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    due = (received_total - paid).quantize(Decimal("0.01"))
    if amount > due:
        raise ValidationError({"amount": f"Payment exceeds the unpaid value of received goods ({due})."})
    payment = SupplierPayment.objects.create(
        tenant_id=po.tenant_id, purchase_order=po, amount=amount, method=method,
        reference=reference, idempotency_key=key, recorded_by=user,
    )
    post_supplier_payment_expense(payment=payment, user=user)
    return payment, False


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



@transaction.atomic
def record_supplier_invoice(*, po, reference, invoice_date, due_date, amount,
                            user, membership, note=""):
    """Record a verified supplier document; never invent a cash payment.

    Multiple partial-delivery invoices are supported up to the known value of
    received goods. Missing receipt costs require confirmation first.
    """
    po = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    if not outlet_belongs_to_membership(membership, po.outlet_id):
        raise ValidationError({"detail": "You cannot record invoices for this section."})
    if po.status not in (PurchaseOrderStatus.PARTIALLY_RECEIVED, PurchaseOrderStatus.RECEIVED):
        raise ValidationError({"detail": "Receive goods before adding an invoice."})
    number = (reference or "").strip()
    if not number or len(number) > 128:
        raise ValidationError({"reference": "Enter a supplier invoice number, up to 128 characters."})
    description = (note or "").strip()
    if len(description) > 512:
        raise ValidationError({"note": "Use at most 512 characters."})
    if due_date < invoice_date:
        raise ValidationError({"due_date": "Due date cannot be earlier than invoice date."})
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise ValidationError({"amount": "Enter a positive amount with two decimal places."})
    existing = SupplierInvoice.objects.filter(
        tenant_id=po.tenant_id, purchase_order=po, reference=number,
    ).first()
    if existing is not None:
        if (existing.amount, existing.invoice_date, existing.due_date, existing.note) != (
                amount, invoice_date, due_date, description):
            raise ValidationError({"reference": "Invoice number already used for different details."})
        return existing, True
    if po.lines.filter(quantity_received__gt=0, unit_cost__isnull=True).exists():
        raise ValidationError({"detail": "Confirm unit costs of received goods before adding an invoice."})
    value = received_goods_value(po)
    already = po.invoices.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    if amount > value - already:
        raise ValidationError({
            "amount": "Invoice exceeds the unbilled value of received goods; review any tax or delivery charges separately."
        })
    invoice = SupplierInvoice.objects.create(
        tenant_id=po.tenant_id, purchase_order=po, reference=number,
        invoice_date=invoice_date, due_date=due_date, amount=amount,
        note=description, recorded_by=user,
    )
    log_audit(
        tenant_id=po.tenant_id, user_id=user.pk if user else None,
        action="purchase.supplier_invoice_recorded",
        entity_type="supplier_invoice", entity_id=str(invoice.pk),
        payload={
            "purchase_order_id": str(po.pk), "reference": number,
            "amount": str(amount), "due_date": str(due_date),
        },
    )
    return invoice, False
