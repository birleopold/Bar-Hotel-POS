"""Atomic retail return and tender refund workflow."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.pos.models import Order, OrderLine, Refund, SupermarketLineReturn
from apps.tenants.models import OutletType

from .orders import process_supermarket_line_return
from .payments import record_order_refund


def refund_retail_line(*, order: Order, line: OrderLine, quantity: Decimal,
                       amount: Decimal, reason: str, restock: bool, user,
                       idempotency_key: str, payment_id=None, workstation_id=None, shift_id=None,
                       serial_numbers=None) -> tuple[SupermarketLineReturn, bool]:
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
    # Reject malformed input before opening a database transaction.
    # The lock, posting and audit sequence remains a single atomic unit.
    with transaction.atomic():
        locked = Order.objects.select_for_update().select_related("outlet").get(pk=order.pk)
        if locked.outlet.outlet_type not in {OutletType.RETAIL, OutletType.SUPERMARKET}:
            raise ValidationError("Line refunds are only available for retail and supermarket orders.")
        if line.order_id != locked.id:
            raise ValidationError({"line_id": "That line is not on this order."})
        # A return cannot refund more than the sold line's recorded net amount
        # and tax, proportioned to the quantity being returned. This uses the
        # immutable order line snapshot, not today's potentially changed price.
        # Final total/payment caps continue to be enforced by record_order_refund.
        line_snapshot = OrderLine.objects.select_for_update().get(pk=line.pk, order_id=locked.pk)
        if line_snapshot.quantity <= 0:
            raise ValidationError({"quantity": "Original sale has no refundable quantity."})
        remaining_return_value = (
            (line_snapshot.line_total + line_snapshot.tax_amount)
            * quantity / line_snapshot.quantity
        ).quantize(Decimal("0.01"))
        if amount > remaining_return_value:
            raise ValidationError({
                "amount": "Refund exceeds the original amount for the returned quantity."
            })
        # A replay must verify the physical return as well as the tender refund.
        existing = Refund.objects.filter(tenant_id=locked.tenant_id, idempotency_key=idempotency_key.strip()).first() if idempotency_key else None
        if existing is not None:
            ret = SupermarketLineReturn.objects.filter(refund=existing).first()
            if (ret is None or ret.order_id != locked.id or ret.order_line_id != line.id
                    or ret.quantity != quantity or ret.restocked != restock
                    or ret.reason != (reason or "")[:255]):
                raise ValidationError({"Idempotency-Key": "This key was already used for a different return."})
            if line.menu_item_id and line.menu_item.serial_tracking:
                from apps.inventory.services_serials import normalize_serial_numbers
                supplied = {value.casefold() for value in normalize_serial_numbers(serial_numbers)}
                linked = {
                    value.casefold()
                    for value in ret.serialized_unit_links.values_list(
                        "serial_unit__serial_number", flat=True
                    )
                }
                if supplied != linked:
                    raise ValidationError({
                        "Idempotency-Key": "This refund key was already used with different serial / IMEI values."
                    })
        refund, replay = record_order_refund(
            order=locked, user=user, amount=amount, reason=reason,
            idempotency_key=idempotency_key, restock=False, payment_id=payment_id,
            workstation_id=workstation_id, shift_id=shift_id,
        )
        if replay:
            return ret, True
        ret = process_supermarket_line_return(
            order=locked, line=line, quantity=quantity, reason=reason,
            restock=restock, user=user, serial_numbers=serial_numbers,
        )
        ret.refund = refund
        ret.save(update_fields=["refund", "updated_at"])
        return ret, False
