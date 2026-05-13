from decimal import Decimal

from django.db.models import Sum

from apps.pos.models import Order


def line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return (quantity * unit_price).quantize(Decimal("0.01"))


def line_tax(line_subtotal: Decimal, tax_rate_percent) -> Decimal:
    if tax_rate_percent is None:
        return Decimal("0.00")
    rate = Decimal(str(tax_rate_percent))
    return (line_subtotal * rate / Decimal("100")).quantize(Decimal("0.01"))


def recalculate_order_totals(order: Order) -> None:
    agg = order.lines.filter(is_voided=False).aggregate(s=Sum("line_total"), t=Sum("tax_amount"))
    subtotal = agg["s"] or Decimal("0.00")
    tax_total = agg["t"] or Decimal("0.00")
    order.subtotal = subtotal
    order.tax_total = tax_total
    disc = order.discount_amount or Decimal("0.00")
    raw = subtotal + tax_total - disc
    order.total = max(Decimal("0.00"), raw).quantize(Decimal("0.01"))
    order.save(update_fields=["subtotal", "tax_total", "total", "updated_at"])
