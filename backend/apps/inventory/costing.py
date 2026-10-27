"""Authoritative retail inventory cost-basis helpers.

Cost is outlet-specific and updated from physical purchase receipts. Legacy or
otherwise uncosted on-hand stock remains explicitly incomplete rather than
being silently valued from a later receipt.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import StockBalance


COST_QUANT = Decimal("0.0001")
QTY_QUANT = Decimal("0.001")


def normalize_unit_cost(value) -> Decimal:
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"unit_cost": "Enter a valid non-negative unit cost."}) from exc
    if not cost.is_finite() or cost < 0 or cost > Decimal("9999999999.9999"):
        raise ValidationError({"unit_cost": "Enter a valid non-negative unit cost."})
    return cost.quantize(COST_QUANT, rounding=ROUND_HALF_UP)


@transaction.atomic
def apply_receipt_cost_basis(
    *,
    tenant_id,
    outlet,
    menu_item,
    quantity_received,
    unit_cost,
) -> StockBalance:
    """Update weighted average cost after the matching stock receipt is posted.

    The caller must have already increased StockBalance by quantity_received in
    the same outer transaction. This function locks that row again and derives
    the pre-receipt quantity from the post-receipt balance.
    """
    try:
        qty = Decimal(str(quantity_received)).quantize(QTY_QUANT)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"quantity_received": "Enter a valid received quantity."}) from exc
    if qty <= 0:
        raise ValidationError({"quantity_received": "Received quantity must be positive."})

    balance = StockBalance.objects.select_for_update().get(
        tenant_id=tenant_id,
        outlet=outlet,
        menu_item=menu_item,
    )
    if balance.quantity < qty:
        raise ValidationError({"cost": "Stock balance is lower than the posted receipt quantity."})

    old_qty = (balance.quantity - qty).quantize(QTY_QUANT)
    if unit_cost is None:
        # Missing supplier cost means the full balance is not safe for margin
        # protection, even when this was the first receipt.
        balance.average_unit_cost = None
        balance.cost_basis_complete = False
    else:
        receipt_cost = normalize_unit_cost(unit_cost)
        if old_qty == 0:
            balance.average_unit_cost = receipt_cost
            balance.cost_basis_complete = True
        elif balance.cost_basis_complete and balance.average_unit_cost is not None:
            old_value = old_qty * balance.average_unit_cost
            receipt_value = qty * receipt_cost
            balance.average_unit_cost = (
                (old_value + receipt_value) / balance.quantity
            ).quantize(COST_QUANT, rounding=ROUND_HALF_UP)
            balance.cost_basis_complete = True
        else:
            # Existing legacy/uncosted units make the blended balance unknown.
            # Do not invent an average from the new receipt alone.
            balance.average_unit_cost = None
            balance.cost_basis_complete = False

    balance.save(update_fields=[
        "average_unit_cost", "cost_basis_complete", "updated_at",
    ])
    return balance


def authoritative_unit_cost(balance: StockBalance) -> Decimal | None:
    if not balance.cost_basis_complete or balance.average_unit_cost is None:
        return None
    return balance.average_unit_cost
