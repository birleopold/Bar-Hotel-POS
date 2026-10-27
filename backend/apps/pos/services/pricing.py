from decimal import Decimal

from django.db.models import Sum

from apps.catalog.promotion_rules import promotion_matches_item
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
) -> Decimal:
    """Recompute the current applied-promotion discount from live basket lines.

    The promotion identity remains attached to the open basket. If a target or
    minimum subtotal temporarily stops qualifying, the discount becomes zero
    and will recover automatically if the basket qualifies again before
    payment starts.
    """
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
    basis = subtotal
    if scoped:
        basis = Decimal("0.00")
        for line in (
            order.lines.select_related("menu_item")
            .filter(is_voided=False, menu_item__isnull=False)
            .order_by("sort_order")
        ):
            if promotion_matches_item(promotion, line.menu_item):
                basis += line.line_total
        basis = basis.quantize(Decimal("0.01"))
        if basis <= 0:
            return Decimal("0.00")

    if promotion.discount_percent is not None:
        discount = (
            basis * promotion.discount_percent / Decimal("100")
        ).quantize(Decimal("0.01"))
    elif promotion.discount_amount is not None:
        discount = promotion.discount_amount.quantize(Decimal("0.01"))
    else:
        return Decimal("0.00")

    ceiling = basis if scoped else subtotal + tax_total
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
