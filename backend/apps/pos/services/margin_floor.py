"""Retail gross-margin floor policy backed only by trusted outlet inventory cost."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from apps.inventory.models import StockBalance
from apps.tenants.models import OutletType, TenantSettings


RETAIL_OUTLET_TYPES = {OutletType.RETAIL, OutletType.SUPERMARKET}


@dataclass(frozen=True)
class MarginFloorResult:
    enforced: bool
    cost_complete: bool
    floor_percent: Decimal | None
    minimum_unit_price: Decimal | None
    proposed_unit_price: Decimal | None
    breach: bool
    reason: str = ""


def configured_margin_floor(order) -> Decimal | None:
    if order.outlet.outlet_type not in RETAIL_OUTLET_TYPES:
        return None
    try:
        value = order.tenant.settings.retail_min_margin_percent
    except TenantSettings.DoesNotExist:
        return None
    return Decimal(str(value)) if value is not None else None


def minimum_unit_price_for_cost(cost: Decimal, floor_percent: Decimal) -> Decimal:
    denominator = Decimal("1") - (floor_percent / Decimal("100"))
    return (cost / denominator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def line_margin_floor_result(*, order, line, proposed_unit_price) -> MarginFloorResult:
    floor = configured_margin_floor(order)
    proposed = Decimal(str(proposed_unit_price)).quantize(Decimal("0.01"))
    if floor is None or not line.menu_item_id or not line.menu_item.track_inventory:
        return MarginFloorResult(False, False, floor, None, proposed, False)

    balance = StockBalance.objects.filter(
        tenant_id=order.tenant_id,
        outlet_id=order.outlet_id,
        menu_item_id=line.menu_item_id,
    ).only("average_unit_cost", "cost_basis_complete").first()
    if balance is None or not balance.cost_basis_complete or balance.average_unit_cost is None:
        return MarginFloorResult(True, False, floor, None, proposed, False)

    minimum = minimum_unit_price_for_cost(balance.average_unit_cost, floor)
    breach = proposed < minimum
    return MarginFloorResult(
        True,
        True,
        floor,
        minimum,
        proposed,
        breach,
        (
            f"Minimum gross margin is {floor}%: this item cannot sell below "
            f"{order.currency} {minimum:.2f} without a manager override."
            if breach else ""
        ),
    )


def promotion_margin_floor_result(*, order, discount_amount) -> tuple[bool, str]:
    """Conservative basket-level guard for automatic promotions.

    Enforce only when every inventory-tracked merchandise line affected by the
    basket has a complete outlet cost basis. Incomplete cost never creates a
    fake approval/block.
    """
    floor = configured_margin_floor(order)
    if floor is None:
        return False, ""
    lines = list(
        order.lines.select_related("menu_item").filter(
            is_voided=False,
            menu_item__isnull=False,
        )
    )
    tracked = [line for line in lines if line.menu_item.track_inventory]
    if not tracked:
        return False, ""

    balances = {
        row.menu_item_id: row
        for row in StockBalance.objects.filter(
            tenant_id=order.tenant_id,
            outlet_id=order.outlet_id,
            menu_item_id__in=[line.menu_item_id for line in tracked],
        ).only("menu_item_id", "average_unit_cost", "cost_basis_complete")
    }
    if any(
        line.menu_item_id not in balances
        or not balances[line.menu_item_id].cost_basis_complete
        or balances[line.menu_item_id].average_unit_cost is None
        for line in tracked
    ):
        return False, ""

    merchandise_revenue = sum(
        (line.line_total for line in lines), Decimal("0.00")
    ) - Decimal(str(discount_amount))
    merchandise_cost = sum(
        (
            line.quantity * balances[line.menu_item_id].average_unit_cost
            for line in tracked
        ),
        Decimal("0.00"),
    )
    if merchandise_revenue <= 0:
        return True, (
            f"This offer would breach the configured {floor}% minimum gross margin."
        )
    actual_margin = (
        (merchandise_revenue - merchandise_cost)
        / merchandise_revenue
        * Decimal("100")
    )
    if actual_margin < floor:
        return True, (
            f"This offer would reduce the basket gross margin to {actual_margin.quantize(Decimal('0.01'))}% "
            f"below the configured {floor}% floor."
        )
    return False, ""
