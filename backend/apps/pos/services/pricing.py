from decimal import Decimal

from django.db.models import Sum

from apps.catalog.models import Promotion
from apps.catalog.promotion_rules import (
    promotion_matches_item,
    promotion_qualifying_quantity,
    promotion_reward_matches_item,
    promotion_reward_quantity,
)
from apps.pos.models import Order


def line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return (quantity * unit_price).quantize(Decimal("0.01"))


def line_tax(line_subtotal: Decimal, tax_rate_percent) -> Decimal:
    if tax_rate_percent is None:
        return Decimal("0.00")
    rate = Decimal(str(tax_rate_percent))
    return (line_subtotal * rate / Decimal("100")).quantize(Decimal("0.01"))


def promotion_discount_for_order(
    order: Order,
    *,
    subtotal: Decimal,
    tax_total: Decimal,
    promotion_override: Promotion | None = None,
) -> Decimal:
    """Recompute the current applied-promotion discount from live basket lines.

    The promotion identity remains attached to the open basket. If a target or
    minimum subtotal temporarily stops qualifying, the discount becomes zero
    and will recover automatically if the basket qualifies again before
    payment starts.
    """
    promotion = promotion_override
    if promotion is None:
        if not order.applied_promotion_id:
            return Decimal("0.00")
        promotion = order.applied_promotion
    if promotion.min_order_subtotal is not None and subtotal < promotion.min_order_subtotal:
        return Decimal("0.00")

    scoped = bool(
        promotion.menu_item_id
        or promotion.product_family_id
        or promotion.category_id
        or (promotion.brand or "").strip()
    )
    if (
        promotion.min_target_quantity is not None
        and promotion_qualifying_quantity(promotion, order) < promotion.min_target_quantity
    ):
        return Decimal("0.00")

    active_lines = list(
        order.lines.select_related("menu_item")
        .filter(is_voided=False, menu_item__isnull=False)
        .order_by("sort_order")
    )
    eligible_lines = [
        line for line in active_lines
        if promotion_matches_item(promotion, line.menu_item)
    ] if scoped else active_lines

    basis = subtotal
    if scoped:
        basis = sum((line.line_total for line in eligible_lines), Decimal("0.00")).quantize(Decimal("0.01"))
        if basis <= 0:
            return Decimal("0.00")

    if promotion.offer_type == Promotion.OfferType.BUY_X_GET_Y:
        if not scoped or not eligible_lines:
            return Decimal("0.00")
        reward_is_separate = bool(
            promotion.reward_menu_item_id
            or promotion.reward_product_family_id
            or promotion.reward_category_id
            or (promotion.reward_brand or "").strip()
        )
        reward_lines = [
            line for line in active_lines
            if promotion_reward_matches_item(promotion, line.menu_item)
        ]
        if not reward_lines:
            return Decimal("0.00")
        if reward_is_separate and any(
            promotion_matches_item(promotion, line.menu_item)
            and promotion_reward_matches_item(promotion, line.menu_item)
            for line in active_lines
        ):
            return Decimal("0.00")
        if any(
            line.quantity != line.quantity.to_integral_value()
            for line in eligible_lines + reward_lines
        ):
            return Decimal("0.00")
        buy_qty = int(promotion.buy_quantity or 0)
        get_qty = int(promotion.get_quantity or 0)
        if buy_qty <= 0 or get_qty <= 0:
            return Decimal("0.00")
        buy_units = sum(int(line.quantity) for line in eligible_lines)
        reward_units = sum(int(line.quantity) for line in reward_lines)
        if reward_is_separate:
            uses = min(buy_units // buy_qty, reward_units // get_qty)
        else:
            set_size = buy_qty + get_qty
            if set_size <= 1:
                return Decimal("0.00")
            uses = buy_units // set_size
        if promotion.max_uses_per_order is not None:
            uses = min(uses, promotion.max_uses_per_order)
        if uses <= 0:
            return Decimal("0.00")
        remaining_free = uses * get_qty
        discount = Decimal("0.00")
        priced = sorted(
            (
                ((line.line_total / line.quantity).quantize(Decimal("0.01")), int(line.quantity))
                for line in reward_lines
                if line.quantity > 0
            ),
            key=lambda row: row[0],
        )
        for per_unit, available_units in priced:
            if remaining_free <= 0:
                break
            take = min(remaining_free, available_units)
            discount += per_unit * take
            remaining_free -= take
        if remaining_free:
            return Decimal("0.00")
        discount = discount.quantize(Decimal("0.01"))
    elif promotion.offer_type == Promotion.OfferType.X_FOR_FIXED_AMOUNT:
        if not scoped or not eligible_lines:
            return Decimal("0.00")
        if any(line.quantity != line.quantity.to_integral_value() for line in eligible_lines):
            return Decimal("0.00")
        fixed_quantity = int(promotion.fixed_quantity or 0)
        fixed_amount = promotion.fixed_bundle_amount
        if fixed_quantity <= 0 or fixed_amount is None or fixed_amount <= 0:
            return Decimal("0.00")
        total_units = sum(int(line.quantity) for line in eligible_lines)
        uses = total_units // fixed_quantity
        if promotion.max_uses_per_order is not None:
            uses = min(uses, promotion.max_uses_per_order)
        if uses <= 0:
            return Decimal("0.00")
        units_needed = uses * fixed_quantity
        priced_units = []
        for line in eligible_lines:
            if line.quantity <= 0:
                continue
            per_unit = (line.line_total / line.quantity).quantize(Decimal("0.01"))
            priced_units.extend([per_unit] * int(line.quantity))
        priced_units.sort()
        qualifying_value = sum(priced_units[:units_needed], Decimal("0.00")).quantize(Decimal("0.01"))
        deal_value = (fixed_amount * uses).quantize(Decimal("0.01"))
        discount = max(Decimal("0.00"), qualifying_value - deal_value).quantize(Decimal("0.01"))
    elif promotion.discount_percent is not None:
        discount = (
            basis * promotion.discount_percent / Decimal("100")
        ).quantize(Decimal("0.01"))
    elif promotion.discount_amount is not None:
        discount = promotion.discount_amount.quantize(Decimal("0.01"))
    else:
        return Decimal("0.00")

    ceiling = basis if scoped else subtotal + tax_total
    if (
        promotion.offer_type == Promotion.OfferType.BUY_X_GET_Y
        and scoped
        and (
            promotion.reward_menu_item_id
            or promotion.reward_product_family_id
            or promotion.reward_category_id
            or (promotion.reward_brand or "").strip()
        )
    ):
        # Cross-target BOGO discounts reward merchandise, which can legitimately
        # be worth more than the qualifying pool. Cap at the live reward value,
        # not the buy-side basis.
        ceiling = sum(
            (line.line_total for line in reward_lines),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
    return min(discount, ceiling).quantize(Decimal("0.01"))


def recalculate_order_totals(order: Order) -> None:
    agg = order.lines.filter(is_voided=False).aggregate(s=Sum("line_total"), t=Sum("tax_amount"))
    subtotal = agg["s"] or Decimal("0.00")
    tax_total = agg["t"] or Decimal("0.00")
    order.subtotal = subtotal
    order.tax_total = tax_total
    disc = (
        promotion_discount_for_order(order, subtotal=subtotal, tax_total=tax_total)
        if order.applied_promotion_id
        else (order.discount_amount or Decimal("0.00"))
    )
    order.discount_amount = disc
    raw = subtotal + tax_total - disc
    order.total = max(Decimal("0.00"), raw).quantize(Decimal("0.01"))
    order.save(update_fields=["subtotal", "tax_total", "discount_amount", "total", "updated_at"])
