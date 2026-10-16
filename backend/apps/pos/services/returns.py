"""Atomic retail return and tender refund workflow."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.pos.models import Order, OrderLine, Refund, SupermarketLineReturn
from apps.tenants.models import OutletType

from .orders import process_supermarket_line_return
from .payments import record_order_refund


@transaction.atomic
def refund_retail_line(*, order: Order, line: OrderLine, quantity: Decimal,
                       amount: Decimal, reason: str, restock: bool, user,
                       idempotency_key: str, payment_id=None, workstation_id=None, shift_id=None) -> tuple[SupermarketLineReturn, bool]:
    # Fail with a user-facing error before touching any refund, loyalty or
    # stock record. Reject NaN/Infinity, negative and excessive precision.
    try:
        quantity = Decimal(str(quantity))
        amount = Decimal(str(amount))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValidationError({"refund": "Enter valid numeric return quantity and refund amount."}) from exc
    if (not quantity.is_finite() or quantity <= 0 or
            quantity > Decimal("99999999999.999") or
            quantity != quantity.quantize(Decimal("0.001"))):
        raise ValidationError({"quantity": "Return quantity must be positive with up to three decimal places."})
    if (not amount.is_finite() or amount <= 0 or
            amount > Decimal("9999999999.99") or
            amount != amount.quantize(Decimal("0.01"))):
        raise ValidationError({"amount": "Refund amount must be positive with up to two decimal places."})
    locked = Order.objects.select_for_update().select_related("outlet").get(pk=order.pk)
    if locked.outlet.outlet_type not in {OutletType.RETAIL, OutletType.SUPERMARKET}:
        raise ValidationError("Line refunds are only available for retail and supermarket orders.")
    if line.order_id != locked.id:
        raise ValidationError({"line_id": "That line is not on this order."})
    # A replay must verify the physical return as well as the tender refund.
    existing = Refund.objects.filter(tenant_id=locked.tenant_id, idempotency_key=idempotency_key.strip()).first() if idempotency_key else None
    if existing is not None:
        ret = SupermarketLineReturn.objects.filter(refund=existing).first()
        if (ret is None or ret.order_id != locked.id or ret.order_line_id != line.id
                or ret.quantity != quantity or ret.restocked != restock
                or ret.reason != (reason or "")[:255]):
            raise ValidationError({"Idempotency-Key": "This key was already used for a different return."})
    refund, replay = record_order_refund(
        order=locked, user=user, amount=amount, reason=reason,
        idempotency_key=idempotency_key, restock=False, payment_id=payment_id,
        workstation_id=workstation_id, shift_id=shift_id,
    )
    if replay:
        return ret, True
    ret = process_supermarket_line_return(
        order=locked, line=line, quantity=quantity, reason=reason,
        restock=restock, user=user,
    )
    ret.refund = refund
    ret.save(update_fields=["refund", "updated_at"])
    return ret, False
