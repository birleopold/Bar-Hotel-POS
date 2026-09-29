from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.finance.services import post_pos_payment_income, post_pos_refund_expense
from apps.inventory.models import StockReason
from apps.inventory.services import apply_manual_stock_change, validate_and_consume_stock_for_paid_order
from apps.lodging.models import Folio, FolioLine, FolioStatus
from apps.pos.models import KdsLineStatus, Order, OrderStatus, Payment, Refund
from apps.tenants.models import OutletType


def _is_kitchen_section_station(station: str | None) -> bool:
    token = (station or "").strip().lower()
    if token in {"bar", "drinks", "beverage", "bartender"}:
        return False
    if token in {"service", "spa", "steam", "sauna", "lodging", "frontdesk", "front_desk"}:
        return False
    return True


@transaction.atomic
def record_order_payment(
    *,
    order: Order,
    user,
    amount: Decimal,
    method: str,
    idempotency_key: str,
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

    payment = Payment.objects.create(
        tenant_id=locked.tenant_id,
        order=locked,
        amount=amount,
        method=method,
        idempotency_key=idempotency_key,
        recorded_by=user,
    )
    post_pos_payment_income(payment=payment, order=locked, user=user)
    new_paid = (paid_so_far + amount).quantize(Decimal("0.01"))
    if new_paid >= locked.total:
        # Guard close-out until kitchen/food lines have been prepared.
        if locked.outlet.outlet_type in {
            OutletType.RESTAURANT,
            OutletType.BAR,
            OutletType.LOUNGE,
            OutletType.CAFETERIA,
        }:
            pending_kitchen_exists = locked.lines.filter(
                is_voided=False,
                kds_status__in=[KdsLineStatus.PENDING, KdsLineStatus.IN_PREP],
            )
            pending_kitchen_exists = any(_is_kitchen_section_station(ln.kds_station) for ln in pending_kitchen_exists)
            if pending_kitchen_exists:
                raise ValidationError(
                    "Order cannot be closed yet: kitchen food items are still pending/in prep. Mark them ready first."
                )
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
            "amount": str(amount),
            "method": method,
            "folio_id": str(locked.folio_id) if locked.folio_id else None,
            "fully_paid": locked.is_paid,
        },
    )
    return payment, False


def _restock_paid_order_tracked_lines(*, order: Order, user) -> None:
    tenant_id = order.tenant_id
    outlet = order.outlet
    for line in order.lines.filter(is_voided=False, menu_item__isnull=False).select_related(
        "menu_item"
    ):
        if not line.menu_item.track_inventory:
            continue
        apply_manual_stock_change(
            tenant_id=tenant_id,
            outlet=outlet,
            menu_item=line.menu_item,
            quantity_change=line.quantity,
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
        if prior_refunds_order > 0:
            raise ValidationError({"restock": "Restock is only allowed when there are no prior refunds."})
        if amount != paid_total:
            raise ValidationError(
                {"restock": "Restock requires refunding the full amount paid on the order in one step."}
            )

    refund = Refund.objects.create(
        tenant_id=locked.tenant_id,
        order=locked,
        payment=payment,
        amount=amount,
        reason=(reason or "")[:255],
        idempotency_key=idempotency_key,
        recorded_by=user,
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
            "amount": str(amount),
            "restock": restock,
        },
    )
    return refund, False
