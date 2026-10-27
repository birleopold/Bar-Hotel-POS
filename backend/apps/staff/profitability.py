"""Historical merchandise profitability from immutable sale-time cost snapshots.

This report deliberately does not substitute current average cost for a sale
whose cost snapshot was incomplete. It reports coverage so management can tell
known gross profit from unknown cost exposure.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Max
from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.pos.models import Order, OrderLine, Refund, SupermarketLineReturn


MONEY = Decimal("0.01")
PERCENT = Decimal("0.1")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _line_net_revenue(line: OrderLine) -> Decimal:
    """Sale-time line revenue before tax after proportional order discount."""
    gross = _money(line.line_total)
    subtotal = _money(line.order.subtotal)
    discount = _money(line.order.discount_amount)
    if gross <= 0 or subtotal <= 0 or discount <= 0:
        return gross
    allocated = (discount * gross / subtotal).quantize(MONEY, rounding=ROUND_HALF_UP)
    return max(Decimal("0.00"), gross - min(gross, allocated))


def build_merchandise_profitability(
    *,
    tenant_id,
    date_from: date,
    date_to: date,
    allowed_outlet_ids,
    currency: str,
    business_date_site=None,
) -> dict:
    if business_date_site is not None:
        from datetime import timedelta
        from apps.tenants.business_date import business_day_window
        start, _ = business_day_window(
            tenant=business_date_site.tenant,
            site=business_date_site,
            operating_date=date_from,
        )
        _, end_exclusive = business_day_window(
            tenant=business_date_site.tenant,
            site=business_date_site,
            operating_date=date_to,
        )
        end = end_exclusive - timedelta(microseconds=1)
    else:
        start, end = utc_day_range_inclusive(date_from, date_to)
    currency = (currency or "UGX").strip().upper()

    # Recognize merchandise revenue once, on the order's final POS payment.
    # This prevents a basket paid in installments across different report dates
    # from contributing its full line revenue to every partial-payment period.
    completed_orders = (
        Order.objects.filter(
            tenant_id=tenant_id,
            outlet_id__in=allowed_outlet_ids,
            is_paid=True,
        )
        .annotate(final_payment_at=Max("payments__created_at"))
        .filter(
            final_payment_at__gte=start,
            final_payment_at__lte=end,
        )
    )
    foreign_payment_count = completed_orders.exclude(currency=currency).count()
    paid_order_ids = list(
        completed_orders.filter(currency=currency)
        .values_list("id", flat=True)
    )

    line_qs = (
        OrderLine.objects.filter(
            order_id__in=paid_order_ids,
            is_voided=False,
            menu_item__isnull=False,
            menu_item__track_inventory=True,
        )
        .select_related("order", "menu_item", "menu_item__category")
        .order_by("order_id", "sort_order", "created_at")
    )

    totals = {
        "currency": currency,
        "sale_revenue": Decimal("0.00"),
        "sale_units": Decimal("0"),
        "covered_sale_revenue": Decimal("0.00"),
        "covered_sale_units": Decimal("0"),
        "known_sale_cogs": Decimal("0.00"),
        "return_revenue": Decimal("0.00"),
        "covered_return_revenue": Decimal("0.00"),
        "return_units": Decimal("0"),
        "known_restock_cogs_reversal": Decimal("0.00"),
        "incomplete_sale_lines": 0,
        "incomplete_restock_return_lines": 0,
        "unmapped_refund_amount": Decimal("0.00"),
        "unmapped_refund_count": 0,
        "foreign_currency_payment_count": foreign_payment_count,
    }
    def _blank_profit_row():
        return {
            "sale_revenue": Decimal("0.00"),
            "sale_units": Decimal("0"),
            "covered_revenue": Decimal("0.00"),
            "covered_units": Decimal("0"),
            "known_cogs": Decimal("0.00"),
            "return_revenue": Decimal("0.00"),
            "covered_return_revenue": Decimal("0.00"),
            "return_units": Decimal("0"),
            "known_cogs_reversal": Decimal("0.00"),
            "incomplete_lines": 0,
            "incomplete_return_lines": 0,
        }

    products = defaultdict(lambda: {
        "item_name": "",
        "sku": "",
        **_blank_profit_row(),
    })
    categories = defaultdict(lambda: {
        "category_name": "",
        **_blank_profit_row(),
    })

    for line in line_qs.iterator(chunk_size=500):
        revenue = _line_net_revenue(line)
        trusted = (
            line.cost_basis_complete_snapshot
            and line.cost_unit_snapshot is not None
        )
        row = products[line.menu_item_id]
        row["item_name"] = line.menu_item.name
        row["sku"] = line.menu_item.sku or ""
        category_id = line.menu_item.category_id or "uncategorized"
        category_row = categories[category_id]
        category_row["category_name"] = (
            line.menu_item.category.name
            if line.menu_item.category_id else "Uncategorized"
        )
        row["sale_revenue"] += revenue
        category_row["sale_revenue"] += revenue
        row["sale_units"] += line.quantity
        category_row["sale_units"] += line.quantity
        totals["sale_revenue"] += revenue
        totals["sale_units"] += line.quantity
        if trusted:
            cogs = (line.quantity * line.cost_unit_snapshot).quantize(
                MONEY, rounding=ROUND_HALF_UP
            )
            row["covered_revenue"] += revenue
            row["covered_units"] += line.quantity
            row["known_cogs"] += cogs
            category_row["covered_revenue"] += revenue
            category_row["covered_units"] += line.quantity
            category_row["known_cogs"] += cogs
            totals["covered_sale_revenue"] += revenue
            totals["covered_sale_units"] += line.quantity
            totals["known_sale_cogs"] += cogs
        else:
            row["incomplete_lines"] += 1
            category_row["incomplete_lines"] += 1
            totals["incomplete_sale_lines"] += 1

    returns_qs = (
        SupermarketLineReturn.objects.filter(
            tenant_id=tenant_id,
            created_at__gte=start,
            created_at__lte=end,
            order__outlet_id__in=allowed_outlet_ids,
            order__currency=currency,
        )
        .select_related(
            "order_line",
            "order_line__order",
            "order_line__menu_item",
            "order_line__menu_item__category",
        )
    )
    mapped_refund_ids = set()
    for returned in returns_qs.iterator(chunk_size=500):
        line = returned.order_line
        if not line.menu_item_id or not line.menu_item.track_inventory:
            continue
        if returned.refund_id:
            mapped_refund_ids.add(returned.refund_id)
        unit_revenue = (
            _line_net_revenue(line) / line.quantity
            if line.quantity > 0 else Decimal("0")
        )
        revenue_reversal = (unit_revenue * returned.quantity).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
        trusted = (
            line.cost_basis_complete_snapshot
            and line.cost_unit_snapshot is not None
        )
        row = products[line.menu_item_id]
        row["item_name"] = line.menu_item.name
        row["sku"] = line.menu_item.sku or ""
        category_id = line.menu_item.category_id or "uncategorized"
        category_row = categories[category_id]
        category_row["category_name"] = (
            line.menu_item.category.name
            if line.menu_item.category_id else "Uncategorized"
        )
        row["return_revenue"] += revenue_reversal
        category_row["return_revenue"] += revenue_reversal
        row["return_units"] += returned.quantity
        category_row["return_units"] += returned.quantity
        totals["return_revenue"] += revenue_reversal
        totals["return_units"] += returned.quantity
        if trusted:
            row["covered_return_revenue"] += revenue_reversal
            category_row["covered_return_revenue"] += revenue_reversal
            totals["covered_return_revenue"] += revenue_reversal
        if returned.restocked:
            if trusted:
                cogs_reversal = (
                    returned.quantity * line.cost_unit_snapshot
                ).quantize(MONEY, rounding=ROUND_HALF_UP)
                row["known_cogs_reversal"] += cogs_reversal
                category_row["known_cogs_reversal"] += cogs_reversal
                totals["known_restock_cogs_reversal"] += cogs_reversal
            else:
                row["incomplete_return_lines"] += 1
                category_row["incomplete_return_lines"] += 1
                totals["incomplete_restock_return_lines"] += 1

    refund_qs = Refund.objects.filter(
        tenant_id=tenant_id,
        created_at__gte=start,
        created_at__lte=end,
        order__outlet_id__in=allowed_outlet_ids,
        order__currency=currency,
    )
    refund_order_ids = list(refund_qs.values_list("order_id", flat=True).distinct())
    inventory_refund_order_ids = set(
        OrderLine.objects.filter(
            order_id__in=refund_order_ids,
            is_voided=False,
            menu_item__track_inventory=True,
        ).values_list("order_id", flat=True).distinct()
    )
    unmapped = refund_qs.filter(
        order_id__in=inventory_refund_order_ids,
    ).exclude(pk__in=mapped_refund_ids)
    totals["unmapped_refund_count"] = unmapped.count()
    totals["unmapped_refund_amount"] = _money(
        sum(unmapped.values_list("amount", flat=True), Decimal("0.00"))
    )

    totals["sale_revenue"] = _money(totals["sale_revenue"])
    totals["covered_sale_revenue"] = _money(totals["covered_sale_revenue"])
    totals["known_sale_cogs"] = _money(totals["known_sale_cogs"])
    totals["return_revenue"] = _money(totals["return_revenue"])
    totals["covered_return_revenue"] = _money(
        totals["covered_return_revenue"]
    )
    totals["known_restock_cogs_reversal"] = _money(
        totals["known_restock_cogs_reversal"]
    )
    totals["net_merchandise_revenue"] = _money(
        totals["sale_revenue"] - totals["return_revenue"]
    )
    totals["known_net_cogs"] = _money(
        totals["known_sale_cogs"] - totals["known_restock_cogs_reversal"]
    )

    def _finalize_row(row):
        row["sale_revenue"] = _money(row["sale_revenue"])
        row["covered_revenue"] = _money(row["covered_revenue"])
        row["known_cogs"] = _money(row["known_cogs"])
        row["return_revenue"] = _money(row["return_revenue"])
        row["covered_return_revenue"] = _money(row["covered_return_revenue"])
        row["known_cogs_reversal"] = _money(row["known_cogs_reversal"])
        # Physical return revenue is known from the original sale line even
        # when the sale happened before this reporting period. Cost uncertainty
        # matters only when a restocked return needs an unknown COGS reversal.
        row["covered_net_revenue"] = _money(
            row["covered_revenue"] - row["covered_return_revenue"]
        )
        row["known_net_cogs"] = _money(
            row["known_cogs"] - row["known_cogs_reversal"]
        )
        row["known_gross_profit"] = _money(
            row["covered_net_revenue"] - row["known_net_cogs"]
        )
        row["known_margin_percent"] = (
            (
                row["known_gross_profit"] / row["covered_net_revenue"]
                * Decimal("100")
            ).quantize(PERCENT, rounding=ROUND_HALF_UP)
            if row["covered_net_revenue"] > 0 else None
        )
        row["net_revenue"] = _money(
            row["sale_revenue"] - row["return_revenue"]
        )
        row["uncovered_net_revenue"] = _money(
            row["net_revenue"] - row["covered_net_revenue"]
        )
        return row

    product_rows = [_finalize_row(row) for row in products.values()]
    category_rows = [_finalize_row(row) for row in categories.values()]
    covered_net_revenue = sum(
        (row["covered_net_revenue"] for row in product_rows),
        Decimal("0.00"),
    )

    totals["covered_net_revenue"] = _money(covered_net_revenue)
    totals["uncovered_net_revenue"] = _money(
        totals["net_merchandise_revenue"] - totals["covered_net_revenue"]
    )
    totals["known_gross_profit"] = _money(
        totals["covered_net_revenue"] - totals["known_net_cogs"]
    )
    totals["known_margin_percent"] = (
        (
            totals["known_gross_profit"]
            / totals["covered_net_revenue"]
            * Decimal("100")
        ).quantize(PERCENT, rounding=ROUND_HALF_UP)
        if totals["covered_net_revenue"] > 0 else None
    )
    totals["cost_coverage_percent"] = (
        (
            totals["covered_sale_revenue"]
            / totals["sale_revenue"]
            * Decimal("100")
        ).quantize(PERCENT, rounding=ROUND_HALF_UP)
        if totals["sale_revenue"] > 0 else Decimal("100.0")
    )
    totals["profitability_complete"] = bool(
        totals["incomplete_sale_lines"] == 0
        and totals["incomplete_restock_return_lines"] == 0
        and totals["unmapped_refund_count"] == 0
        and totals["foreign_currency_payment_count"] == 0
    )
    product_rows.sort(
        key=lambda row: (
            -row["net_revenue"],
            row["item_name"].lower(),
        )
    )
    category_rows.sort(
        key=lambda row: (
            -row["net_revenue"],
            row["category_name"].lower(),
        )
    )
    totals["products"] = product_rows[:25]
    totals["categories"] = category_rows[:25]
    return totals
