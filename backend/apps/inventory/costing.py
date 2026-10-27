"""Authoritative retail inventory cost-basis helpers.

Cost is outlet-specific and updated from physical purchase receipts. Legacy or
otherwise uncosted on-hand stock remains explicitly incomplete rather than
being silently valued from a later receipt.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit

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
def apply_inbound_cost_basis(
    *,
    tenant_id,
    outlet,
    menu_item,
    quantity_received,
    unit_cost,
    incoming_cost_complete: bool,
) -> StockBalance:
    """Blend one already-posted stock increase into the outlet cost basis."""
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
        raise ValidationError({"cost": "Stock balance is lower than the posted inbound quantity."})

    old_qty = (balance.quantity - qty).quantize(QTY_QUANT)
    incoming_cost = (
        normalize_unit_cost(unit_cost)
        if incoming_cost_complete and unit_cost is not None
        else None
    )
    if incoming_cost is None:
        balance.average_unit_cost = None
        balance.cost_basis_complete = False
    elif old_qty == 0:
        balance.average_unit_cost = incoming_cost
        balance.cost_basis_complete = True
    elif balance.cost_basis_complete and balance.average_unit_cost is not None:
        old_value = old_qty * balance.average_unit_cost
        incoming_value = qty * incoming_cost
        balance.average_unit_cost = (
            (old_value + incoming_value) / balance.quantity
        ).quantize(COST_QUANT, rounding=ROUND_HALF_UP)
        balance.cost_basis_complete = True
    else:
        # Existing legacy/uncosted units make the blended balance unknown.
        balance.average_unit_cost = None
        balance.cost_basis_complete = False

    balance.save(update_fields=[
        "average_unit_cost", "cost_basis_complete", "updated_at",
    ])
    return balance


def apply_receipt_cost_basis(
    *,
    tenant_id,
    outlet,
    menu_item,
    quantity_received,
    unit_cost,
) -> StockBalance:
    """Update weighted average cost from a physical supplier receipt."""
    return apply_inbound_cost_basis(
        tenant_id=tenant_id,
        outlet=outlet,
        menu_item=menu_item,
        quantity_received=quantity_received,
        unit_cost=unit_cost,
        incoming_cost_complete=unit_cost is not None,
    )


def authoritative_unit_cost(balance: StockBalance) -> Decimal | None:
    if not balance.cost_basis_complete or balance.average_unit_cost is None:
        return None
    return balance.average_unit_cost

@transaction.atomic
def reconcile_incomplete_cost_basis(
    *,
    tenant_id,
    outlet,
    menu_item,
    unit_cost,
    reason: str,
    user,
) -> StockBalance:
    """Establish cost for existing on-hand stock without changing quantity.

    This is intentionally limited to incomplete balances. Correcting an already
    trusted cost requires a separate reviewed accounting workflow.
    """
    note = (reason or "").strip()
    if len(note) < 12:
        raise ValidationError({
            "reason": "Describe the cost evidence or reconciliation basis in at least 12 characters."
        })
    cost = normalize_unit_cost(unit_cost)
    balance = StockBalance.objects.select_for_update().filter(
        tenant_id=tenant_id,
        outlet=outlet,
        menu_item=menu_item,
    ).first()
    if balance is None or balance.quantity <= 0:
        raise ValidationError({
            "cost": "There must be positive on-hand stock to reconcile a legacy cost basis."
        })
    if balance.cost_basis_complete and balance.average_unit_cost is not None:
        raise ValidationError({
            "cost": "This stock balance already has a trusted cost basis."
        })

    before = {
        "quantity": str(balance.quantity),
        "average_unit_cost": (
            str(balance.average_unit_cost)
            if balance.average_unit_cost is not None else None
        ),
        "cost_basis_complete": balance.cost_basis_complete,
    }
    balance.average_unit_cost = cost
    balance.cost_basis_complete = True
    balance.save(update_fields=[
        "average_unit_cost", "cost_basis_complete", "updated_at",
    ])
    log_audit(
        tenant_id=tenant_id,
        user_id=user.pk if user else None,
        action="inventory.cost_basis_reconciled",
        entity_type="stock_balance",
        entity_id=str(balance.pk),
        payload={
            "outlet_id": str(outlet.pk),
            "menu_item_id": str(menu_item.pk),
            "reason": note[:512],
            "before": before,
            "after": {
                "quantity": str(balance.quantity),
                "average_unit_cost": str(balance.average_unit_cost),
                "cost_basis_complete": True,
            },
            "quantity_changed": False,
            "historical_sales_rewritten": False,
        },
    )
    return balance

