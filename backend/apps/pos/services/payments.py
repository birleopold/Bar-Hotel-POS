from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.access.outlets import outlet_belongs_to_membership
from apps.catalog.models import MenuItem
from apps.finance.services import post_pos_payment_income, post_pos_refund_expense
from apps.inventory.models import StockMovement, StockReason
from apps.inventory.services import apply_manual_stock_change, validate_and_consume_stock_for_paid_order
from apps.lodging.models import Folio, FolioLine, FolioStatus
from apps.pos.models import KdsLineStatus, Order, OrderStatus, Payment, Refund, SupermarketLineReturn
from apps.tenants.models import OutletType


from .registers import resolve_settlement_shift, check_replay_register


def _is_kitchen_section_station(station: str | None) -> bool:
    token = (station or "").strip().lower()
    if token in {"bar", "drinks", "beverage", "bartender"}:
        return False
    if token in {"service", "spa", "steam", "sauna", "lodging", "frontdesk", "front_desk"}:
        return False
    return True


def _ensure_kitchen_ready(order: Order) -> None:
    if order.outlet.outlet_type not in {
        OutletType.RESTAURANT, OutletType.BAR, OutletType.LOUNGE, OutletType.CAFETERIA,
    }:
        return
    pending = order.lines.filter(
        is_voided=False, kds_status__in=[KdsLineStatus.PENDING, KdsLineStatus.IN_PREP],
    )
    if any(_is_kitchen_section_station(line.kds_station) for line in pending):
        raise ValidationError("Order cannot be closed yet: kitchen food items are still pending/in prep. Mark them ready first.")


@transaction.atomic
def record_order_payment(
    *,
    order: Order,
    user,
    amount: Decimal,
    method: str,
    idempotency_key: str,
    workstation_id=None,
    shift_id=None,
) -> tuple[Payment, bool]:
    if not idempotency_key or not idempotency_key.strip():
        raise ValidationError(
            {"Idempotency-Key": "Required non-empty header Idempotency-Key for payments."}
        )
    idempotency_key = idempotency_key.strip()
    if len(idempotency_key) > 128:
        raise ValidationError({"Idempotency-Key": "Must be at most 128 characters."})

    locked = Order.objects.select_for_update().get(pk=order.pk)

    existing = Payment.objects.filter(
        tenant_id=locked.tenant_id,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        if existing.order_id != locked.id or existing.amount != amount or existing.method != method:
            raise ValidationError(
                {"Idempotency-Key": "This key was already used for a different payment."}
            )
        check_replay_register(existing, workstation_id=workstation_id, shift_id=shift_id)
        return existing, True

    if locked.status != OrderStatus.OPEN:
        raise ValidationError("Payments are only accepted for open orders.")
    if locked.is_paid:
        raise ValidationError("This order is already paid.")

    paid_so_far = (
        Payment.objects.filter(order_id=locked.id).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    )
    remaining = (locked.total - paid_so_far).quantize(Decimal("0.01"))
    if amount <= 0 or amount > remaining:
        raise ValidationError(
            {
                "amount": (
                    f"Payment must be positive and at most remaining balance {remaining} "
                    f"(order total {locked.total}, already paid {paid_so_far})."
                )
            }
        )

    shift = resolve_settlement_shift(order=locked, workstation_id=workstation_id, shift_id=shift_id)
    payment = Payment.objects.create(
        tenant_id=locked.tenant_id,
        order=locked,
        amount=amount,
        method=method,
        idempotency_key=idempotency_key,
        recorded_by=user,
        shift=shift,
    )
    post_pos_payment_income(payment=payment, order=locked, user=user)
    new_paid = (paid_so_far + amount).quantize(Decimal("0.01"))
    if new_paid >= locked.total:
        # Guard close-out until kitchen/food lines have been prepared.
        _ensure_kitchen_ready(locked)
        locked.is_paid = True
        locked.status = OrderStatus.CLOSED
        locked.save(update_fields=["is_paid", "status", "updated_at"])
        validate_and_consume_stock_for_paid_order(locked, user)

        if locked.folio_id:
            folio = Folio.objects.select_for_update().get(pk=locked.folio_id)
            if folio.status != FolioStatus.OPEN or folio.currency != locked.currency:
                raise ValidationError({"folio": "Folio must be open and use the order currency."})
            # The sale was already settled at the POS and posted to finance above.
            # Show it on the guest statement without making it payable twice.
            FolioLine.objects.create(
                tenant_id=locked.tenant_id,
                folio=folio,
                description=f"POS {locked.bill_reference}",
                amount=locked.total - locked.tax_total,
                tax_amount=locked.tax_total,
                source_order=locked,
            )
            FolioLine.objects.create(
                tenant_id=locked.tenant_id,
                folio=folio,
                description=f"Paid at POS {locked.bill_reference}",
                amount=-locked.total,
                source_order=locked,
            )
    else:
        locked.save(update_fields=["updated_at"])

    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="payment.recorded",
        entity_type="order",
        entity_id=str(locked.id),
        payload={
            "payment_id": str(payment.id),
            "shift_id": str(payment.shift_id) if payment.shift_id else None,
            "amount": str(amount),
            "method": method,
            "folio_id": str(locked.folio_id) if locked.folio_id else None,
            "fully_paid": locked.is_paid,
        },
    )
    return payment, False


@transaction.atomic
def charge_order_to_folio(*, order: Order, membership, user) -> FolioLine:
    """Close an open POS order and transfer only its unpaid balance to the guest folio."""
    locked = Order.objects.select_for_update().select_related("outlet__site").get(pk=order.pk)
    if not outlet_belongs_to_membership(membership, locked.outlet_id):
        raise ValidationError({"detail": "You cannot charge an order at this outlet."})
    if locked.status != OrderStatus.OPEN or locked.is_paid or locked.folio_id is None:
        raise ValidationError({"folio": "Attach an open folio to an open, unpaid order first."})
    if locked.total <= 0:
        raise ValidationError({"order": "Add chargeable items before charging a folio."})
    folio = Folio.objects.select_for_update().get(pk=locked.folio_id)
    if (folio.tenant_id != locked.tenant_id or folio.site_id != locked.outlet.site_id
            or folio.status != FolioStatus.OPEN or folio.currency != locked.currency):
        raise ValidationError({"folio": "Folio must be open, in this branch, and use the order currency."})
    paid = Payment.objects.filter(order=locked).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    if paid >= locked.total:
        raise ValidationError({"order": "This order is fully paid at the POS."})
    _ensure_kitchen_ready(locked)
    validate_and_consume_stock_for_paid_order(locked, user)
    charge = FolioLine.objects.create(
        tenant_id=locked.tenant_id, folio=folio, description=f"POS {locked.bill_reference}",
        amount=locked.total - locked.tax_total, tax_amount=locked.tax_total, source_order=locked,
    )
    if paid > 0:
        FolioLine.objects.create(
            tenant_id=locked.tenant_id, folio=folio, description=f"Paid at POS {locked.bill_reference}",
            amount=-paid, source_order=locked,
        )
    locked.status = OrderStatus.CLOSED
    locked.save(update_fields=["status", "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id, user_id=user.id if user else None,
        action="order.charged_to_folio", entity_type="order", entity_id=str(locked.id),
        payload={"folio_id": str(folio.id), "total": str(locked.total), "paid_at_pos": str(paid)},
    )
    return charge


def _restock_paid_order_tracked_lines(*, order: Order, user) -> None:
    # Return only stock that this order actually consumed, regardless of current
    # catalog settings. Account for items already restocked via line returns.
    sold = StockMovement.objects.filter(order=order, reason=StockReason.SALE).values(
        "menu_item_id"
    ).annotate(quantity=Sum("quantity_change"))
    already_returned = dict(
        SupermarketLineReturn.objects.filter(order=order, restocked=True)
        .values("order_line__menu_item_id")
        .annotate(quantity=Sum("quantity"))
        .values_list("order_line__menu_item_id", "quantity")
    )
    for row in sold:
        item_id = row["menu_item_id"]
        quantity = -row["quantity"] - already_returned.get(item_id, Decimal("0"))
        if quantity <= 0:
            continue
        apply_manual_stock_change(
            tenant_id=order.tenant_id,
            outlet=order.outlet,
            menu_item=MenuItem.objects.get(pk=item_id),
            quantity_change=quantity,
            reason=StockReason.ADJUST_IN,
            user=user,
            note=f"Refund restock {order.bill_reference}"[:512],
        )


def _resolve_refund_payment(
    *,
    order: Order,
    payments: list,
    amount: Decimal,
    payment_id,
) -> Payment:
    if len(payments) == 1:
        p = payments[0]
        refunded_on_p = (
            Refund.objects.filter(payment_id=p.id).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        )
        cap = (p.amount - refunded_on_p).quantize(Decimal("0.01"))
        if amount > cap:
            raise ValidationError(
                {"amount": f"Refund exceeds remaining {cap} on the only payment for this order."}
            )
        return p
    if payment_id is None:
        raise ValidationError(
            {"payment_id": "Required when the order has more than one payment (split tender)."}
        )
    p = next((x for x in payments if x.id == payment_id), None)
    if p is None:
        raise ValidationError({"payment_id": "Payment not found on this order."})
    refunded_on_p = (
        Refund.objects.filter(payment_id=p.id).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    )
    cap = (p.amount - refunded_on_p).quantize(Decimal("0.01"))
    if amount > cap:
        raise ValidationError(
            {"amount": f"Refund exceeds remaining {cap} for the selected payment."}
        )
    return p


@transaction.atomic
def record_order_refund(
    *,
    order: Order,
    user,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    restock: bool,
    payment_id=None,
    workstation_id=None,
    shift_id=None,
) -> tuple[Refund, bool]:
    if not idempotency_key or not idempotency_key.strip():
        raise ValidationError(
            {"Idempotency-Key": "Required non-empty header Idempotency-Key for refunds."}
        )
    idempotency_key = idempotency_key.strip()
    if len(idempotency_key) > 128:
        raise ValidationError({"Idempotency-Key": "Must be at most 128 characters."})

    locked = Order.objects.select_for_update().get(pk=order.pk)

    existing = Refund.objects.filter(
        tenant_id=locked.tenant_id,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        if (
            existing.order_id != locked.id
            or existing.amount != amount
            or existing.reason != (reason or "")[:255]
            or existing.restocked != restock
            or (payment_id is not None and existing.payment_id != payment_id)
        ):
            raise ValidationError(
                {"Idempotency-Key": "This key was already used for a different refund."}
            )
        check_replay_register(existing, workstation_id=workstation_id, shift_id=shift_id)
        return existing, True

    if locked.status != OrderStatus.CLOSED or not locked.is_paid:
        raise ValidationError("Refunds are only for closed, paid orders.")

    payments = list(
        Payment.objects.filter(order_id=locked.id, tenant_id=locked.tenant_id).order_by("created_at")
    )
    if not payments:
        raise ValidationError("No payment found for this order.")

    paid_total = sum(p.amount for p in payments)
    prior_refunds_order = (
        Refund.objects.filter(order_id=locked.id).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    )
    refundable_order = (paid_total - prior_refunds_order).quantize(Decimal("0.01"))
    if amount <= 0 or amount > refundable_order:
        raise ValidationError(
            {"amount": f"Refund must be positive and at most remaining {refundable_order}."}
        )

    payment = _resolve_refund_payment(
        order=locked,
        payments=payments,
        amount=amount,
        payment_id=payment_id,
    )

    if restock:
        if Refund.objects.filter(order=locked, restocked=True).exists():
            raise ValidationError({"restock": "This order's stock has already been restocked."})
        if amount + prior_refunds_order != paid_total:
            raise ValidationError(
                {"restock": "Restock is allowed on the final refund when all payments have been refunded."}
            )

    shift = resolve_settlement_shift(order=locked, workstation_id=workstation_id, shift_id=shift_id)
    refund = Refund.objects.create(
        tenant_id=locked.tenant_id,
        order=locked,
        payment=payment,
        amount=amount,
        reason=(reason or "")[:255],
        idempotency_key=idempotency_key,
        recorded_by=user,
        shift=shift,
        restocked=restock,
    )
    post_pos_refund_expense(refund=refund, order=locked, user=user)

    if restock:
        _restock_paid_order_tracked_lines(order=locked, user=user)

    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.refunded",
        entity_type="order",
        entity_id=str(locked.id),
        payload={
            "refund_id": str(refund.id),
            "shift_id": str(refund.shift_id) if refund.shift_id else None,
            "amount": str(amount),
            "restock": restock,
        },
    )
    return refund, False
