from decimal import Decimal, InvalidOperation, ROUND_DOWN

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.audit.models import ExceptionReview
from apps.audit.services import exception_fingerprint, log_audit
from apps.catalog.label_queue import queue_product_label
from apps.catalog.packaging import to_stock_units
from apps.finance.models import FinancePostingLink, FinancePostingSource
from apps.finance.services import post_supplier_payment_expense
from apps.inventory.models import StockMovement, StockReason
from apps.inventory.costing import apply_receipt_cost_basis
from apps.inventory.services import apply_manual_stock_change
from apps.inventory.services_batches import receive_tracked_batch
from apps.inventory.services_serials import create_received_serial_units, validate_serial_receipt
from apps.inventory.batches import InventoryBatch
from django.utils import timezone

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, PurchaseReceipt, PurchaseReceiptLine, Supplier, SupplierPayment, SupplierPaymentMethod, SupplierInvoice, SupplierInvoiceLine, SupplierReturn, SupplierCreditNote


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
    shipping_cost: Decimal = Decimal("0"),
    duty_cost: Decimal = Decimal("0"),
    landed_cost_allocation: str = PurchaseReceipt.LandedCostAllocation.EXCLUDE,
) -> PurchaseOrder:
    if len(discrepancy_note) > 512:
        raise ValidationError({"discrepancy_note": "Use at most 512 characters."})
    try:
        shipping_cost = Decimal(str(shipping_cost or 0)).quantize(Decimal("0.01"))
        duty_cost = Decimal(str(duty_cost or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"landed_cost": "Enter valid shipping and duty amounts."}) from exc
    if (
        not shipping_cost.is_finite()
        or not duty_cost.is_finite()
        or shipping_cost < 0
        or duty_cost < 0
    ):
        raise ValidationError({"landed_cost": "Shipping and duty amounts must be non-negative."})
    if landed_cost_allocation not in PurchaseReceipt.LandedCostAllocation.values:
        raise ValidationError({"landed_cost_allocation": "Choose a supported landed-cost allocation method."})
    if not outlet_belongs_to_membership(membership, po.outlet_id):
        raise ValidationError({"detail": "You cannot receive stock for this outlet."})

    po_locked = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    delivery_reference = (delivery_reference or "").strip()
    if len(delivery_reference) > 128:
        raise ValidationError({"delivery_reference": "Use at most 128 characters."})
    if delivery_reference and PurchaseReceipt.objects.filter(
        purchase_order=po_locked, delivery_reference__iexact=delivery_reference
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
    delivery_serials = set()
    for row in lines_payload:
        try:
            line_id = row["line_id"]
        except (TypeError, KeyError) as exc:
            raise ValidationError({"lines": "Each delivery row needs a purchase order line."}) from exc
        line = PurchaseOrderLine.objects.select_for_update().filter(
            purchase_order=po_locked, pk=line_id,
        ).first()
        if line is None:
            raise ValidationError({"lines": f"Unknown line: {line_id}."})
        try:
            package_value = Decimal(str(row.get("packages") or 0))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError({"lines": f"Enter a valid whole package count for {line.menu_item.name}."}) from exc
        if (
            not package_value.is_finite()
            or package_value < 0
            or package_value != package_value.to_integral_value()
        ):
            raise ValidationError({"lines": f"Package count for {line.menu_item.name} must be a non-negative whole number."})
        package_count = int(package_value)
        carton_count = int(Decimal(str(row.get("cartons") or 0)))
        if package_count and carton_count:
            raise ValidationError({"lines": f"Use packages or cartons for {line.menu_item.name}, not both."})
        if package_count and not line.package_units_snapshot:
            raise ValidationError({"lines": f"{line.menu_item.name} was not ordered with a package snapshot."})
        qty = to_stock_units(
            units=row.get("quantity", 0), cartons=carton_count,
            units_per_carton=line.units_per_carton_snapshot,
            allow_zero=bool(package_count),
        )
        if package_count:
            qty += (Decimal(package_count) * line.package_units_snapshot).quantize(Decimal("0.001"))
            if qty > Decimal("99999999999.999"):
                raise ValidationError({"lines": f"Received quantity for {line.menu_item.name} exceeds stock limits."})
        serials = validate_serial_receipt(
            tenant_id=po_locked.tenant_id,
            outlet=po_locked.outlet,
            menu_item=line.menu_item,
            quantity=qty,
            serial_numbers=row.get("serial_numbers", []),
        )
        for identifier in serials:
            folded = identifier.casefold()
            if folded in delivery_serials:
                raise ValidationError({"serial_numbers": f'Duplicate identifier "{identifier}" across this delivery.'})
            delivery_serials.add(folded)
        normalized.append({
            **row, "line_id": line.pk, "quantity": qty,
            "cartons": carton_count, "packages": package_count,
            "serial_numbers": serials, "_line": line,
        })
    lines_payload = normalized
    positive_ids = [row["line_id"] for row in lines_payload if row["quantity"] > 0]
    if not positive_ids:
        raise ValidationError({"lines": "At least one line must have quantity greater than zero."})
    if len(positive_ids) != len(set(positive_ids)):
        raise ValidationError({"lines": "Each purchase order line may be received only once per delivery."})
    # Preflight the entire physical delivery before any receipt or stock write.
    # The enclosing transaction remains authoritative for all-or-nothing
    # posting, even if a later batch or ledger operation fails.
    for row in lines_payload:
        qty = row["quantity"]
        if qty <= 0:
            continue
        line = row["_line"]
        remaining = line.quantity_ordered - line.quantity_received
        if qty > remaining:
            raise ValidationError({
                "lines": (
                    f"Quantity for line {line.pk} exceeds remaining "
                    f"({remaining} left to receive)."
                )
            })
        batch_code = str(row.get("batch_code") or "").strip()
        if line.menu_item.serial_tracking and (batch_code or row.get("expiry_date")):
            raise ValidationError({
                "batch_code": (
                    f"{line.menu_item.name} is serial / IMEI tracked. "
                    "Do not combine batch/expiry tracking with serialized receipt in this workflow."
                )
            })
        if row.get("expiry_date") and not batch_code:
            raise ValidationError({"batch_code": "Enter a batch code when setting an expiry date."})
        if not batch_code and InventoryBatch.objects.filter(
            tenant_id=po_locked.tenant_id, outlet=po_locked.outlet,
            menu_item=line.menu_item,
        ).exists():
            raise ValidationError({
                "batch_code": f"Enter a batch code for {line.menu_item.name}; this product is batch-tracked."
            })
        if batch_code and InventoryBatch.objects.filter(
            tenant_id=po_locked.tenant_id, outlet=po_locked.outlet,
            menu_item=line.menu_item, batch_code=batch_code,
        ).exists():
            raise ValidationError({
                "batch_code": f"Batch {batch_code} was already received for {line.menu_item.name}."
            })
    positive_rows = [row for row in lines_payload if row["quantity"] > 0]
    total_extra_cost = (shipping_cost + duty_cost).quantize(Decimal("0.01"))
    for row in positive_rows:
        row["_allocated_landed_cost"] = Decimal("0.00")
        row["_landed_unit_cost"] = (
            Decimal(str(row["_line"].unit_cost)).quantize(Decimal("0.0001"))
            if row["_line"].unit_cost is not None
            else None
        )

    if (
        total_extra_cost > 0
        and landed_cost_allocation == PurchaseReceipt.LandedCostAllocation.BY_COST
    ):
        if any(row["_line"].unit_cost is None for row in positive_rows):
            raise ValidationError({
                "landed_cost": (
                    "Every received line needs a supplier unit cost before shipping/duty "
                    "can be distributed into inventory cost."
                )
            })
        base_values = [
            (row["quantity"] * row["_line"].unit_cost).quantize(Decimal("0.01"))
            for row in positive_rows
        ]
        total_base_value = sum(base_values, Decimal("0.00"))
        if total_base_value <= 0:
            raise ValidationError({
                "landed_cost": "Received supplier-cost value must be greater than zero to distribute landed costs."
            })
        allocated_so_far = Decimal("0.00")
        for index, (row, base_value) in enumerate(zip(positive_rows, base_values)):
            if index == len(positive_rows) - 1:
                allocated = total_extra_cost - allocated_so_far
            else:
                allocated = (
                    total_extra_cost * base_value / total_base_value
                ).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                allocated_so_far += allocated
            row["_allocated_landed_cost"] = allocated
            row["_landed_unit_cost"] = (
                row["_line"].unit_cost + (allocated / row["quantity"])
            ).quantize(Decimal("0.0001"))

    receipt = PurchaseReceipt.objects.create(
        tenant_id=po_locked.tenant_id,
        purchase_order=po_locked,
        delivery_reference=delivery_reference,
        note=(note or "")[:512],
        discrepancy_note=discrepancy_note.strip(),
        shipping_cost=shipping_cost,
        duty_cost=duty_cost,
        landed_cost_allocation=landed_cost_allocation,
        received_by=user,
    )

    for row in lines_payload:
        qty: Decimal = row["quantity"]
        if qty <= 0:
            continue
        line = row["_line"]
        batch_code = str(row.get("batch_code") or "").strip()
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
                allow_serialized=line.menu_item.serial_tracking,
            )
        cost_balance = apply_receipt_cost_basis(
            tenant_id=po_locked.tenant_id,
            outlet=po_locked.outlet,
            menu_item=line.menu_item,
            quantity_received=qty,
            unit_cost=row["_landed_unit_cost"],
        )
        line.quantity_received += qty
        line.save(update_fields=["quantity_received", "updated_at"])
        receipt_line = PurchaseReceiptLine.objects.create(
            receipt=receipt,
            purchase_order_line=line,
            quantity_received=qty,
            cartons_received=row["cartons"],
            packages_received=row["packages"],
            unit_cost_snapshot=line.unit_cost,
            landed_unit_cost_snapshot=row["_landed_unit_cost"],
            landed_cost_allocated=row["_allocated_landed_cost"],
            inventory_batch=batch,
        )
        queue_product_label(
            tenant_id=po_locked.tenant_id,
            outlet=po_locked.outlet,
            menu_item=line.menu_item,
            reason="receiving",
            user=user,
            note=f"Goods received on PO {po_locked.reference or po_locked.pk}.",
        )
        if line.menu_item.serial_tracking:
            create_received_serial_units(
                tenant_id=po_locked.tenant_id,
                outlet=po_locked.outlet,
                menu_item=line.menu_item,
                receipt_line=receipt_line,
                received_at=row.get("received_at") or timezone.localdate(),
                serial_numbers=row["serial_numbers"],
                user=user,
            )

    _sync_po_status(po_locked)
    # Trace the delivery itself, including shortages and supplier reference.
    # Individual inventory movements already have their own ledger audits.
    log_audit(
        tenant_id=po_locked.tenant_id,
        user_id=user.pk if user else None,
        action="purchase.goods_received",
        entity_type="purchase_receipt",
        entity_id=str(receipt.pk),
        payload={
            "purchase_order_id": str(po_locked.pk),
            "delivery_reference": delivery_reference,
            "discrepancy_note": receipt.discrepancy_note,
            "shipping_cost": str(receipt.shipping_cost),
            "duty_cost": str(receipt.duty_cost),
            "landed_cost_allocation": receipt.landed_cost_allocation,
            "lines": [
                {"purchase_order_line_id": str(line.purchase_order_line_id),
                 "quantity_received": format(line.quantity_received.normalize(), "f"),
                 "cartons_received": line.cartons_received,
                 "packages_received": line.packages_received,
                 "unit_cost_snapshot": (
                     str(line.unit_cost_snapshot)
                     if line.unit_cost_snapshot is not None else None
                 ),
                 "landed_unit_cost_snapshot": (
                     str(line.landed_unit_cost_snapshot)
                     if line.landed_unit_cost_snapshot is not None else None
                 ),
                 "landed_cost_allocated": str(line.landed_cost_allocated)}
                for line in receipt.lines.all()
            ],
        },
    )
    return po_locked


def received_goods_value(po: PurchaseOrder) -> Decimal:
    gross = sum(
        ((line.quantity_received * line.unit_cost).quantize(Decimal("0.01"))
         for line in po.lines.all() if line.unit_cost is not None),
        Decimal("0"),
    )
    returned = sum(
        ((ret.quantity * ret.receipt_line.purchase_order_line.unit_cost).quantize(Decimal("0.01"))
         for ret in po.returns_to_supplier.select_related("receipt_line__purchase_order_line").all()
         if ret.receipt_line.purchase_order_line.unit_cost is not None),
        Decimal("0"),
    )
    return gross - returned


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
    try:
        unit_cost = Decimal(str(unit_cost))
    except (TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
        raise ValidationError({"unit_cost": "Enter a valid cost amount."}) from exc
    if (not unit_cost.is_finite() or unit_cost < 0
            or unit_cost > Decimal("9999999999.99")
            or unit_cost != unit_cost.quantize(Decimal("0.01"))):
        raise ValidationError({"unit_cost": "Enter a non-negative cost with at most two decimal places."})
    line.unit_cost = unit_cost
    line.save(update_fields=["unit_cost", "updated_at"])
    log_audit(
        tenant_id=po.tenant_id, user_id=user.id if user else None,
        action="purchase.unit_cost_confirmed", entity_type="purchase_order_line", entity_id=str(line.id),
        payload={"purchase_order_id": str(po.id), "unit_cost": str(unit_cost)},
    )
    return line


def _unresolved_delivery_discrepancies(po: PurchaseOrder) -> list[PurchaseReceipt]:
    """Current receipt discrepancies without a resolved manager assessment."""
    unresolved = []
    receipts = PurchaseReceipt.objects.filter(
        tenant_id=po.tenant_id,
        purchase_order=po,
    ).exclude(discrepancy_note="")
    for receipt in receipts:
        fingerprint = exception_fingerprint(
            (receipt.discrepancy_note, receipt.updated_at)
        )
        resolved = ExceptionReview.objects.filter(
            tenant_id=po.tenant_id,
            kind="delivery_discrepancy",
            entity_id=str(receipt.pk),
            fingerprint=fingerprint,
            status="resolved",
        ).exists()
        if not resolved:
            unresolved.append(receipt)
    return unresolved


def record_supplier_payment(
    *, po: PurchaseOrder, amount: Decimal, method: str, reference: str,
    idempotency_key: str, user, membership, invoice_id=None,
) -> tuple[SupplierPayment, bool]:
    try:
        amount = Decimal(str(amount))
    except (TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
        raise ValidationError({"amount": "Enter a valid supplier payment amount."}) from exc
    if (not amount.is_finite() or amount <= 0
            or amount > Decimal("999999999999.99")
            or amount != amount.quantize(Decimal("0.01"))):
        raise ValidationError({"amount": "Enter a positive amount with at most two decimal places."})
    key = (idempotency_key or "").strip()
    if not key or len(key) > 128:
        raise ValidationError({"idempotency_key": "A key of at most 128 characters is required."})
    # Reject malformed input before opening a database transaction.
    # The lock, posting and audit sequence remains a single atomic unit.
    with transaction.atomic():
        po = PurchaseOrder.objects.select_for_update().select_related("outlet__site").get(pk=po.pk)
        if not outlet_belongs_to_membership(membership, po.outlet_id):
            raise ValidationError({"detail": "You cannot pay a supplier for this outlet."})
        reference = (reference or "").strip()
        if len(reference) > 128:
            raise ValidationError({"reference": "Must be at most 128 characters."})
        selected_invoice = None
        if invoice_id:
            selected_invoice = SupplierInvoice.objects.filter(
                tenant_id=po.tenant_id, purchase_order=po, pk=invoice_id,
            ).first()
            if selected_invoice is None:
                raise ValidationError({"invoice_id": "Choose an invoice belonging to this purchase order."})
        existing = SupplierPayment.objects.filter(tenant_id=po.tenant_id, idempotency_key=key).first()
        if existing:
            if (existing.purchase_order_id, existing.amount, existing.method, existing.reference, existing.invoice_id) != (
                po.id, amount, method, reference, selected_invoice.pk if selected_invoice else None
            ):
                raise ValidationError({"idempotency_key": "This key was used for a different supplier payment."})
            return existing, True
        if method not in SupplierPaymentMethod.values:
            raise ValidationError({"method": "Select a valid payment method."})
        unresolved_discrepancies = _unresolved_delivery_discrepancies(po)
        if unresolved_discrepancies:
            raise ValidationError({
                "detail": (
                    "Resolve the recorded delivery discrepancy in Manager → "
                    "Exceptions before paying this supplier."
                )
            })
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
        # Recorded invoices create a narrower settlement ceiling. If no invoice
        # exists, preserve the established receipt-backed payment workflow.
        invoiced = po.invoices.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        credited = po.credits.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        net_invoiced = invoiced - credited
        if invoiced > 0 and amount > (net_invoiced - paid).quantize(Decimal("0.01")):
            raise ValidationError({
                "amount": (
                    "Payment exceeds the unpaid recorded supplier invoices "
                    f"({max(Decimal('0'), net_invoiced - paid):.2f}). "
                    "Record and verify the remaining invoice before paying more."
                )
            })
        if amount > due:
            raise ValidationError({"amount": f"Payment exceeds the unpaid value of received goods ({due})."})
        if selected_invoice is not None:
            # Existing unallocated payments cannot be assigned to a bill by guesswork.
            if po.payments.filter(invoice__isnull=True).exists():
                raise ValidationError({
                    "invoice_id": "This order has payments without invoice attribution. Reconcile them before linking new payments to individual invoices."
                })
            previously_paid = selected_invoice.allocated_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
            invoice_credits = selected_invoice.credits.aggregate(total=Sum("amount"))["total"] or Decimal("0")
            invoice_due = (selected_invoice.amount - invoice_credits - previously_paid).quantize(Decimal("0.01"))
            if amount > invoice_due:
                raise ValidationError({
                    "amount": f"Payment exceeds this invoice's unpaid balance ({max(Decimal('0'), invoice_due):.2f})."
                })
        payment = SupplierPayment.objects.create(
            tenant_id=po.tenant_id, purchase_order=po, invoice=selected_invoice,
            amount=amount, method=method,
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
                            user, membership, note="", lines=None):
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
    from datetime import date
    if not isinstance(invoice_date, date) or not isinstance(due_date, date):
        raise ValidationError({"invoice_date": "Enter valid invoice and payment due dates."})
    if due_date < invoice_date:
        raise ValidationError({"due_date": "Due date cannot be earlier than invoice date."})
    try:
        amount = Decimal(str(amount))
    except (TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
        raise ValidationError({"amount": "Enter a valid supplier invoice amount."}) from exc
    if (not amount.is_finite() or amount <= 0
            or amount > Decimal("999999999999.99")
            or amount != amount.quantize(Decimal("0.01"))):
        raise ValidationError({"amount": "Enter a positive amount with at most two decimal places."})
    # Serialize supplier invoice numbers across all of this supplier's POs.
    # Locking only the purchase order would allow two concurrent POs to accept
    # the same vendor document number.
    Supplier.objects.select_for_update().get(
        pk=po.supplier_id,
        tenant_id=po.tenant_id,
    )
    # Verify actual PO line/receipt evidence before accepting an itemized invoice.
    # Header-only invoices remain as historical/unmatched documents, never
    # retroactively represented as having passed a three-way match.
    existing_invoice = (
        SupplierInvoice.objects.filter(
            tenant_id=po.tenant_id,
            purchase_order__supplier_id=po.supplier_id,
            reference__iexact=number,
        )
        .select_related("purchase_order")
        .first()
    )
    if existing_invoice is not None and existing_invoice.purchase_order_id != po.pk:
        raise ValidationError({
            "reference": (
                "This supplier invoice number is already recorded against "
                "another purchase order."
            )
        })
    matched = []
    if lines is not None:
        if not isinstance(lines, (list, tuple)) or not lines:
            raise ValidationError({"lines": "Include at least one invoiced item and quantity."})
        used = set()
        for entry in lines:
            if not isinstance(entry, dict):
                raise ValidationError({"lines": "Use item, quantity and unit cost for each line."})
            line_id = entry.get("line_id")
            line = PurchaseOrderLine.objects.select_for_update().filter(
                purchase_order=po, pk=line_id,
            ).first()
            if line is None or line.pk in used:
                raise ValidationError({"lines": "Invoice items must be distinct lines on this purchase order."})
            used.add(line.pk)
            if line.unit_cost is None:
                raise ValidationError({"lines": "Confirm the original purchase order unit cost."})
            try:
                qty = Decimal(str(entry.get("quantity")))
                price = Decimal(str(entry.get("unit_cost")))
            except (ValueError, TypeError, ArithmeticError, InvalidOperation) as exc:
                raise ValidationError({"lines": "Enter valid invoiced quantities and prices."}) from exc
            if (not qty.is_finite() or qty <= 0 or qty > Decimal("99999999999.999")
                    or qty != qty.quantize(Decimal("0.001"))):
                raise ValidationError({"lines": "Quantity must be positive and have up to three decimal places."})
            if (not price.is_finite() or price != line.unit_cost):
                raise ValidationError({"lines": f"Unit cost for {line.menu_item.name} differs from the agreed purchase order. Resolve the price difference before paying."})
            previous = line.invoice_matches.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            if existing_invoice is not None:
                own_qty = line.invoice_matches.filter(invoice=existing_invoice).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
                previous -= own_qty
            returned = SupplierReturn.objects.filter(
                purchase_order=po, receipt_line__purchase_order_line=line,
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            if qty > line.quantity_received - returned - previous:
                raise ValidationError({"lines": f"Invoiced quantity for {line.menu_item.name} exceeds accepted, not-yet-invoiced received goods."})
            matched.append((line, qty, price, (qty * price).quantize(Decimal("0.01"))))
        expected = sum((row[3] for row in matched), Decimal("0"))
        if expected != amount:
            raise ValidationError({"amount": f"Invoice amount {amount:.2f} does not equal matched line total {expected:.2f}. Verify supplier charges separately."})
    existing = existing_invoice
    if existing is not None:
        if (existing.amount, existing.invoice_date, existing.due_date, existing.note) != (
                amount, invoice_date, due_date, description):
            raise ValidationError({"reference": "Invoice number already used for different details."})
        if lines is not None:
            old = sorted(
                ((m.purchase_order_line_id, m.quantity, m.unit_cost, m.amount)
                 for m in existing.matched_lines.all()), key=lambda entry: str(entry[0]),
            )
            proposed = sorted(
                ((line.pk, qty, cost, total) for line, qty, cost, total in matched),
                key=lambda entry: str(entry[0]),
            )
            if old != proposed:
                raise ValidationError({"reference": "An invoice with this number has different matched items."})
        return existing, True
    if po.lines.filter(quantity_received__gt=0, unit_cost__isnull=True).exists():
        raise ValidationError({"detail": "Confirm unit costs of received goods before adding an invoice."})
    value = received_goods_value(po)
    already = po.invoices.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    credited = po.credits.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    if amount > value - (already - credited):
        raise ValidationError({
            "amount": "Invoice exceeds the unbilled value of received goods; review any tax or delivery charges separately."
        })
    invoice = SupplierInvoice.objects.create(
        tenant_id=po.tenant_id, purchase_order=po, reference=number,
        invoice_date=invoice_date, due_date=due_date, amount=amount,
        note=description, recorded_by=user,
    )
    for line, qty, cost, total in matched:
        SupplierInvoiceLine.objects.create(
            invoice=invoice, purchase_order_line=line,
            quantity=qty, unit_cost=cost, amount=total,
        )
    log_audit(
        tenant_id=po.tenant_id, user_id=user.pk if user else None,
        action="purchase.supplier_invoice_recorded",
        entity_type="supplier_invoice", entity_id=str(invoice.pk),
        payload={
            "purchase_order_id": str(po.pk), "reference": number,
            "amount": str(amount), "due_date": str(due_date),
            "three_way_matched": bool(matched),
            "matched_lines": [{"po_line": str(l.pk), "quantity": str(q), "unit_cost": str(cost)} for l, q, cost, _ in matched],
        },
    )
    return invoice, False



@transaction.atomic
def record_supplier_credit_note(*, po, invoice_id, reference, credit_date,
                                amount, reason, user, membership):
    """Recognize a vendor credit against unpaid invoices, not a cash refund.

    All invoice, payment and credit changes serialize on the purchase order.
    Historical payments and stock movements are never rewritten.
    """
    from datetime import date

    po = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    if not outlet_belongs_to_membership(membership, po.outlet_id):
        raise ValidationError({"detail": "You cannot record credits for this section."})
    invoice = SupplierInvoice.objects.filter(
        tenant_id=po.tenant_id, purchase_order=po, pk=invoice_id,
    ).first()
    if invoice is None:
        raise ValidationError({"invoice_id": "Choose a supplier invoice on this purchase order."})
    if has_legacy_receipt_expenses(po):
        raise ValidationError({"detail": "Reconcile legacy receipt expenses before recording supplier credits."})
    number = (reference or "").strip()
    if not number or len(number) > 128:
        raise ValidationError({"reference": "Enter the supplier's credit note number (up to 128 characters)."})
    reason = (reason or "").strip()
    if len(reason) < 12 or len(reason) > 512:
        raise ValidationError({"reason": "Explain the supplier credit in 12–512 characters."})
    if not isinstance(credit_date, date) or credit_date < invoice.invoice_date:
        raise ValidationError({"credit_date": "Credit note date cannot be before the invoice date."})
    try:
        amount = Decimal(str(amount))
    except (TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
        raise ValidationError({"amount": "Enter a valid supplier credit amount."}) from exc
    if (not amount.is_finite() or amount <= 0
            or amount > Decimal("999999999999.99")
            or amount != amount.quantize(Decimal("0.01"))):
        raise ValidationError({"amount": "Use a positive credit amount with two decimal places."})
    existing = po.credits.filter(reference=number).first()
    if existing is not None:
        if (existing.invoice_id, existing.credit_date, existing.amount, existing.reason) != (
            invoice.pk, credit_date, amount, reason,
        ):
            raise ValidationError({"reference": "Credit number already used for different details."})
        return existing, True
    credited_for_invoice = invoice.credits.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    gross_invoiced = po.invoices.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_credited = po.credits.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    paid = po.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    invoice_paid = invoice.allocated_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    if amount > invoice.amount - credited_for_invoice - invoice_paid:
        raise ValidationError({"amount": "Credit exceeds the invoice's unpaid balance after linked payments."})
    if amount > gross_invoiced - total_credited - paid:
        raise ValidationError({
            "amount": "Credit would exceed unpaid supplier invoices. Reconcile actual payments/refunds separately."
        })
    credit = SupplierCreditNote.objects.create(
        tenant_id=po.tenant_id, purchase_order=po, invoice=invoice,
        reference=number, credit_date=credit_date, amount=amount,
        reason=reason, recorded_by=user,
    )
    log_audit(
        tenant_id=po.tenant_id, user_id=user.pk if user else None,
        action="purchase.supplier_credit_recorded",
        entity_type="supplier_credit_note", entity_id=str(credit.pk),
        payload={
            "purchase_order_id": str(po.pk), "invoice_id": str(invoice.pk),
            "reference": number, "amount": str(amount), "reason": reason,
            "cash_refunded": False, "stock_changed": False,
        },
    )
    return credit, False



@transaction.atomic
def link_existing_supplier_payment_to_invoice(*, po, payment_id, invoice_id, note, user, membership):
    """Audited attribution correction only: never recreate a cash expense or edit a payment amount.

    Supports one existing PO payment paying one exact invoice in full or part.
    Splitting one historical payment across multiple bills needs a separate
    allocation model and is deliberately not guessed by this operation.
    """
    from apps.staff.services.permissions import membership_has_purchasing_capability

    po = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    if (
        membership is None or membership.tenant_id != po.tenant_id
        or not membership_has_purchasing_capability(membership, "supplier_payment")
        or not outlet_belongs_to_membership(membership, po.outlet_id)
    ):
        raise ValidationError({"detail": "Only an authorized purchasing manager can link payments for this section."})
    payment = po.payments.select_for_update().filter(
        pk=payment_id, tenant_id=po.tenant_id,
    ).first()
    invoice = po.invoices.filter(pk=invoice_id, tenant_id=po.tenant_id).first()
    if payment is None or invoice is None:
        raise ValidationError({"invoice_id": "Select a payment and an invoice from this purchase order."})
    if payment.invoice_id:
        if payment.invoice_id == invoice.pk:
            return payment, True
        raise ValidationError({"payment_id": "This payment is already linked to a different supplier invoice."})
    note = (note or "").strip()
    if not 12 <= len(note) <= 512:
        raise ValidationError({"note": "Explain how the payment reference matches this invoice (12–512 characters)."})
    credited = invoice.credits.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    linked = invoice.allocated_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    due = (invoice.amount - credited - linked).quantize(Decimal("0.01"))
    if payment.amount > due:
        raise ValidationError({
            "invoice_id": "This payment exceeds the invoice's currently unpaid balance. Do not guess a split across invoices."
        })
    payment.invoice = invoice
    payment.save(update_fields=["invoice", "updated_at"])
    log_audit(
        tenant_id=po.tenant_id, user_id=user.pk if user else None,
        action="purchase.supplier_payment_linked_invoice",
        entity_type="supplier_payment", entity_id=str(payment.pk),
        payload={
            "purchase_order_id": str(po.pk),
            "supplier_invoice_id": str(invoice.pk),
            "payment_amount_unchanged": str(payment.amount),
            "previous_invoice_id": None, "reason": note,
            "cashbook_reposted": False, "stock_changed": False,
        },
    )
    return payment, False


@transaction.atomic
def return_received_goods_to_supplier(*, po, receipt_line_id, quantity, reference, note, user, membership):
    """Send physically held goods back to vendor; vendor credit/cash are separate."""
    from apps.staff.services.permissions import membership_has_purchasing_capability
    from apps.inventory.models import StockBalance
    from apps.inventory.services_batches import record_batch_allocations
    from django.db.models import F

    po = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
    if (membership is None or membership.tenant_id != po.tenant_id
            or not membership_has_purchasing_capability(membership, "manage")
            or not outlet_belongs_to_membership(membership, po.outlet_id)):
        raise ValidationError({"detail": "A purchasing manager with access to this section must approve a supplier return."})
    number = (reference or "").strip()
    note = (note or "").strip()
    if not number or len(number) > 128:
        raise ValidationError({"reference": "Enter a supplier return reference up to 128 characters."})
    if not 12 <= len(note) <= 512:
        raise ValidationError({"note": "Explain the physical return in 12–512 characters."})
    try:
        qty = Decimal(str(quantity))
    except (TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
        raise ValidationError({"quantity": "Enter a valid returned quantity."}) from exc
    if (not qty.is_finite() or qty <= 0 or qty > Decimal("99999999999.999")
            or qty != qty.quantize(Decimal("0.001"))):
        raise ValidationError({"quantity": "Quantity must be positive and have up to three decimal places."})
    receipt_line = PurchaseReceiptLine.objects.select_for_update().filter(
        pk=receipt_line_id, receipt__purchase_order=po, receipt__tenant_id=po.tenant_id,
    ).select_related("purchase_order_line__menu_item", "inventory_batch").first()
    if receipt_line is None:
        raise ValidationError({"receipt_line_id": "Select a received delivery line on this PO."})
    previous = po.returns_to_supplier.filter(reference__iexact=number).first()
    if previous is not None:
        if previous.receipt_line_id == receipt_line.pk and previous.quantity == qty and previous.note == note:
            return previous, True
        raise ValidationError({"reference": "This supplier return reference was already used for different goods."})
    returned = receipt_line.supplier_returns.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    if qty > receipt_line.quantity_received - returned:
        raise ValidationError({"quantity": "Returned quantity exceeds the outstanding accepted delivery quantity."})
    item = receipt_line.purchase_order_line.menu_item
    bal = StockBalance.objects.select_for_update().filter(
        outlet=po.outlet, menu_item=item, tenant_id=po.tenant_id,
    ).first()
    if bal is None or bal.quantity < qty:
        raise ValidationError({"stock": "Not enough physical stock remains in the receiving section for this supplier return."})
    tracked = InventoryBatch.objects.filter(
        tenant_id=po.tenant_id, outlet=po.outlet, menu_item=item,
    ).exists()
    if tracked and receipt_line.inventory_batch_id is None:
        raise ValidationError({"batch": "Cannot identify the original received lot; reconcile this historical stock before returning."})
    if tracked:
        batch = InventoryBatch.objects.select_for_update().get(
            pk=receipt_line.inventory_batch_id, tenant_id=po.tenant_id,
            outlet=po.outlet, menu_item=item,
        )
        if batch.remaining_quantity < qty:
            raise ValidationError({"batch": "The originally received lot no longer contains enough units to return."})
        InventoryBatch.objects.filter(pk=batch.pk).update(
            remaining_quantity=F("remaining_quantity") - qty,
        )
        bal.quantity -= qty
        bal.save(update_fields=["quantity", "updated_at"])
        movement = StockMovement.objects.create(
            tenant_id=po.tenant_id, outlet=po.outlet, menu_item=item,
            quantity_change=-qty, reason=StockReason.ADJUST_OUT,
            purchase_order=po, created_by=user,
            note=("Supplier return " + number + ": " + note)[:512],
        )
        record_batch_allocations(tenant_id=po.tenant_id, movement=movement, allocations=[(batch.pk, qty)])
    else:
        movement = apply_manual_stock_change(
            tenant_id=po.tenant_id, outlet=po.outlet, menu_item=item,
            quantity_change=-qty, reason=StockReason.ADJUST_OUT,
            purchase_order=po, user=user, note="Supplier return " + number + ": " + note,
        )
    ret = SupplierReturn.objects.create(
        tenant_id=po.tenant_id, purchase_order=po, receipt_line=receipt_line,
        movement=movement, reference=number, quantity=qty,
        note=note, returned_by=user,
    )
    log_audit(
        tenant_id=po.tenant_id, user_id=user.pk if user else None,
        action="purchase.supplier_goods_returned", entity_type="supplier_return",
        entity_id=str(ret.pk), payload={
            "purchase_order_id": str(po.pk), "receipt_line_id": str(receipt_line.pk),
            "batch_id": str(receipt_line.inventory_batch_id) if receipt_line.inventory_batch_id else None,
            "stock_movement_id": str(movement.pk), "reference": number,
            "quantity": str(qty), "supplier_credit_issued": False, "cash_refunded": False,
            "note": note,
        },
    )
    return ret, False
