"""Sales aggregates for staff HTML (same rules as ``SalesSummaryView``)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum

from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.pos.models import Order, OrderLine, Payment, Refund


WEEKDAY_LABELS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


def _line_section_from_station(station: str | None) -> str:
    token = (station or "").strip().lower()
    if token in {"bar", "drinks", "beverage", "bartender"}:
        return "bar"
    if token in {"service", "spa", "steam", "sauna", "lodging", "frontdesk", "front_desk"}:
        return "service"
    return "kitchen"


SECTION_LABELS = {
    "kitchen": "Kitchen / food",
    "bar": "Bar / drinks",
    "service": "Services",
}


def _staff_label(first_name: str, last_name: str, email: str | None) -> str:
    name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return name or (email or "Unassigned")


def build_sales_summary(
    tenant_id: uuid.UUID,
    d0: date,
    d1: date,
    outlet_id: uuid.UUID | None = None,
    *,
    allowed_outlet_ids: list[uuid.UUID] | None = None,
    outlet_ids: list[uuid.UUID] | None = None,
    business_date_site=None,
) -> dict:
    if business_date_site is not None:
        from apps.tenants.business_date import business_day_window, effective_business_clock
        start, _ = business_day_window(
            tenant=business_date_site.tenant, site=business_date_site, operating_date=d0,
        )
        _, end_exclusive = business_day_window(
            tenant=business_date_site.tenant, site=business_date_site, operating_date=d1,
        )
        end = end_exclusive - timedelta(microseconds=1)
        business_zone, cutover_hour, _ = effective_business_clock(
            tenant=business_date_site.tenant, site=business_date_site,
        )
    else:
        start, end = utc_day_range_inclusive(d0, d1)
        business_zone = None
        cutover_hour = 0

    payments_qs = Payment.objects.filter(
        tenant_id=tenant_id,
        created_at__gte=start,
        created_at__lte=end,
    ).select_related("order", "order__outlet")

    if allowed_outlet_ids is not None:
        payments_qs = payments_qs.filter(order__outlet_id__in=allowed_outlet_ids)
    if outlet_id is not None:
        payments_qs = payments_qs.filter(order__outlet_id=outlet_id)
    elif outlet_ids is not None:
        payments_qs = payments_qs.filter(order__outlet_id__in=outlet_ids)

    pay_agg = payments_qs.aggregate(
        payment_count=Count("id"),
        gross_sales=Sum("amount"),
    )
    gross = pay_agg["gross_sales"] or Decimal("0.00")
    pay_count = pay_agg["payment_count"] or 0

    refunds_qs = Refund.objects.filter(
        tenant_id=tenant_id,
        created_at__gte=start,
        created_at__lte=end,
    ).select_related("order")
    if allowed_outlet_ids is not None:
        refunds_qs = refunds_qs.filter(order__outlet_id__in=allowed_outlet_ids)
    if outlet_id is not None:
        refunds_qs = refunds_qs.filter(order__outlet_id=outlet_id)
    elif outlet_ids is not None:
        refunds_qs = refunds_qs.filter(order__outlet_id__in=outlet_ids)

    ref_agg = refunds_qs.aggregate(
        refund_count=Count("id"),
        refund_total=Sum("amount"),
    )
    ref_total = ref_agg["refund_total"] or Decimal("0.00")
    ref_count = ref_agg["refund_count"] or 0

    by_method_raw = list(
        payments_qs.values("method").annotate(count=Count("id"), amount=Sum("amount")).order_by("method")
    )
    by_method = [
        {
            "method": r["method"],
            "count": r["count"],
            "amount": r["amount"] or Decimal("0.00"),
        }
        for r in by_method_raw
    ]

    by_outlet_raw = list(
        payments_qs.values("order__outlet_id", "order__outlet__name")
        .annotate(count=Count("id"), amount=Sum("amount"))
        .order_by("order__outlet__name")
    )
    by_outlet = [
        {
            "outlet_id": r["order__outlet_id"],
            "outlet_name": r["order__outlet__name"],
            "count": r["count"],
            "amount": r["amount"] or Decimal("0.00"),
        }
        for r in by_outlet_raw
    ]

    paid_order_ids = list(payments_qs.values_list("order_id", flat=True).distinct())
    refund_order_ids = list(refunds_qs.values_list("order_id", flat=True).distinct())
    profitability_order_ids = sorted(
        set(paid_order_ids) | set(refund_order_ids),
        key=str,
    )

    # Profitability is intentionally based on historical cost snapshots captured
    # when stock posted for each sale. Current StockBalance cost must never be
    # back-applied to historical sales.
    payment_by_order: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for order_id, amount in payments_qs.values_list("order_id", "amount"):
        payment_by_order[order_id] += amount or Decimal("0.00")
    refund_by_order: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for order_id, amount in refunds_qs.values_list("order_id", "amount"):
        refund_by_order[order_id] += amount or Decimal("0.00")

    profitability_orders = {
        row["id"]: row
        for row in Order.objects.filter(
            tenant_id=tenant_id,
            pk__in=profitability_order_ids,
        ).values("id", "subtotal", "tax_total", "total", "discount_amount")
    }
    profitability_lines = list(
        OrderLine.objects.filter(
            order_id__in=profitability_order_ids,
            is_voided=False,
            menu_item__isnull=False,
        )
        .select_related("menu_item")
        .values(
            "order_id",
            "menu_item_id",
            "menu_item__track_inventory",
            "label",
            "quantity",
            "line_total",
            "cost_unit_snapshot",
            "cost_basis_complete_snapshot",
        )
    )

    profitability_lines_by_order: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for row in profitability_lines:
        profitability_lines_by_order[row["order_id"]].append(row)

    profit_known_revenue = Decimal("0.00")
    profit_unknown_revenue = Decimal("0.00")
    profit_known_cogs = Decimal("0.00")
    coverage_known_activity = Decimal("0.00")
    coverage_total_activity = Decimal("0.00")
    profit_complete_lines = 0
    profit_incomplete_lines = 0
    refund_allocation_used = False
    incomplete_items: dict[tuple[uuid.UUID | None, str], dict] = {}

    for order_id in profitability_order_ids:
        order_row = profitability_orders.get(order_id)
        if not order_row:
            continue
        order_total = (order_row["total"] or Decimal("0.00")).quantize(Decimal("0.01"))
        order_pre_tax_total = (
            (order_row["subtotal"] or Decimal("0.00"))
            - (order_row["discount_amount"] or Decimal("0.00"))
        ).quantize(Decimal("0.01"))
        if order_total <= 0 or order_pre_tax_total <= 0:
            continue

        payment_amount = payment_by_order.get(order_id, Decimal("0.00"))
        refund_amount = refund_by_order.get(order_id, Decimal("0.00"))
        if refund_amount > 0:
            refund_allocation_used = True

        # Keep the profitability period aligned with this report's payment/refund
        # date basis, while removing tax proportionally.
        pre_tax_ratio = order_pre_tax_total / order_total
        period_pre_tax_net = (
            (payment_amount - refund_amount) * pre_tax_ratio
        ).quantize(Decimal("0.01"))
        activity_pre_tax = (
            (payment_amount + refund_amount) * pre_tax_ratio
        ).copy_abs().quantize(Decimal("0.01"))
        period_factor = period_pre_tax_net / order_pre_tax_total
        activity_factor = activity_pre_tax / order_pre_tax_total

        rows = profitability_lines_by_order.get(order_id, [])
        merchandise_total = sum(
            (
                row["line_total"] or Decimal("0.00")
                for row in rows
                if row["menu_item__track_inventory"]
            ),
            Decimal("0.00"),
        )
        if merchandise_total <= 0:
            continue

        known_line_revenue = Decimal("0.00")
        unknown_line_revenue = Decimal("0.00")
        known_order_cogs = Decimal("0.00")
        for row in rows:
            if not row["menu_item__track_inventory"]:
                continue
            line_revenue = row["line_total"] or Decimal("0.00")
            cost_complete = bool(
                row["cost_basis_complete_snapshot"]
                and row["cost_unit_snapshot"] is not None
            )
            if cost_complete:
                profit_complete_lines += 1
                known_line_revenue += line_revenue
                known_order_cogs += (
                    row["quantity"] * row["cost_unit_snapshot"]
                )
            else:
                profit_incomplete_lines += 1
                unknown_line_revenue += line_revenue
                key = (row["menu_item_id"], row["label"] or "Unknown item")
                item = incomplete_items.setdefault(
                    key,
                    {
                        "item_id": row["menu_item_id"],
                        "item_name": row["label"] or "Unknown item",
                        "lines_count": 0,
                        "revenue": Decimal("0.00"),
                    },
                )
                item["lines_count"] += 1
                item["revenue"] += line_revenue * activity_factor

        # Order-level discounts and order/payment-level refunds are allocated
        # proportionally across merchandise. We expose this assumption in UI.
        merchandise_share = merchandise_total / (
            sum((row["line_total"] or Decimal("0.00") for row in rows), Decimal("0.00"))
            or merchandise_total
        )
        merchandise_period_net = period_pre_tax_net * merchandise_share
        merchandise_activity = activity_pre_tax * merchandise_share
        known_share = known_line_revenue / merchandise_total
        unknown_share = unknown_line_revenue / merchandise_total

        profit_known_revenue += merchandise_period_net * known_share
        profit_unknown_revenue += merchandise_period_net * unknown_share
        profit_known_cogs += known_order_cogs * period_factor
        coverage_known_activity += merchandise_activity * known_share
        coverage_total_activity += merchandise_activity

    profit_known_revenue = profit_known_revenue.quantize(Decimal("0.01"))
    profit_unknown_revenue = profit_unknown_revenue.quantize(Decimal("0.01"))
    profit_known_cogs = profit_known_cogs.quantize(Decimal("0.01"))
    profit_gross = (profit_known_revenue - profit_known_cogs).quantize(Decimal("0.01"))
    profit_margin = (
        (profit_gross / profit_known_revenue * Decimal("100")).quantize(Decimal("0.01"))
        if profit_known_revenue > 0 else None
    )
    cost_coverage_percent = (
        (coverage_known_activity / coverage_total_activity * Decimal("100")).quantize(Decimal("0.01"))
        if coverage_total_activity > 0 else None
    )
    incomplete_items_rows = sorted(
        (
            {
                **item,
                "revenue": item["revenue"].copy_abs().quantize(Decimal("0.01")),
            }
            for item in incomplete_items.values()
        ),
        key=lambda row: (-row["revenue"], row["item_name"].lower()),
    )[:10]

    profitability = {
        "known_net_revenue": profit_known_revenue,
        "unknown_net_revenue": profit_unknown_revenue,
        "known_cogs": profit_known_cogs,
        "known_gross_profit": profit_gross,
        "known_margin_percent": profit_margin,
        "cost_coverage_percent": cost_coverage_percent,
        "complete_lines": profit_complete_lines,
        "incomplete_lines": profit_incomplete_lines,
        "incomplete_items": incomplete_items_rows,
        "refund_allocation_used": refund_allocation_used,
    }

    line_by_order_rows = list(
        OrderLine.objects.filter(order_id__in=paid_order_ids, is_voided=False)
        .values("order_id", "kds_station")
        .annotate(section_total=Sum("line_total"))
    )
    order_section_totals: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))
    order_subtotals: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for row in line_by_order_rows:
        order_id = row["order_id"]
        section = _line_section_from_station(row["kds_station"])
        amount = (row["section_total"] or Decimal("0.00")).quantize(Decimal("0.01"))
        order_section_totals[order_id][section] += amount
        order_subtotals[order_id] += amount

    section_gross_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for order_id, amount in payments_qs.values_list("order_id", "amount"):
        subtotal = (order_subtotals.get(order_id) or Decimal("0.00")).quantize(Decimal("0.01"))
        if subtotal <= Decimal("0.00"):
            continue
        remaining = amount.quantize(Decimal("0.01"))
        section_rows = list(order_section_totals.get(order_id, {}).items())
        for idx, (section, section_total) in enumerate(section_rows):
            if idx == len(section_rows) - 1:
                alloc = remaining
            else:
                alloc = (amount * (section_total / subtotal)).quantize(Decimal("0.01"))
                remaining -= alloc
            section_gross_totals[section] += alloc

    section_refund_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for order_id, amount in refunds_qs.values_list("order_id", "amount"):
        subtotal = (order_subtotals.get(order_id) or Decimal("0.00")).quantize(Decimal("0.01"))
        if subtotal <= Decimal("0.00"):
            continue
        remaining = amount.quantize(Decimal("0.01"))
        section_rows = list(order_section_totals.get(order_id, {}).items())
        for idx, (section, section_total) in enumerate(section_rows):
            if idx == len(section_rows) - 1:
                alloc = remaining
            else:
                alloc = (amount * (section_total / subtotal)).quantize(Decimal("0.01"))
                remaining -= alloc
            section_refund_totals[section] += alloc

    by_section = []
    for key in ("kitchen", "bar", "service"):
        gross_amt = (section_gross_totals.get(key) or Decimal("0.00")).quantize(Decimal("0.01"))
        refund_amt = (section_refund_totals.get(key) or Decimal("0.00")).quantize(Decimal("0.01"))
        net_amt = (gross_amt - refund_amt).quantize(Decimal("0.01"))
        by_section.append(
            {
                "section_key": key,
                "section_label": SECTION_LABELS[key],
                "gross_sales": gross_amt,
                "refunds_total": refund_amt,
                "net_sales": net_amt,
            }
        )

    leaderboard_rows = list(
        payments_qs.values(
            "order__created_by_id",
            "order__created_by__first_name",
            "order__created_by__last_name",
            "order__created_by__email",
        )
        .annotate(
            payments_count=Count("id"),
            orders_count=Count("order_id", distinct=True),
            total_sales=Sum("amount"),
        )
        .order_by("-total_sales", "-orders_count", "order__created_by__email")
    )

    seller_item_rows = list(
        OrderLine.objects.filter(order_id__in=paid_order_ids, is_voided=False)
        .values("order__created_by_id")
        .annotate(items_sold=Sum("quantity"))
    )
    items_sold_by_seller = {
        row["order__created_by_id"]: (row["items_sold"] or Decimal("0")) for row in seller_item_rows
    }

    leaderboard = []
    for index, row in enumerate(leaderboard_rows, start=1):
        seller_id = row["order__created_by_id"]
        total_sales = (row["total_sales"] or Decimal("0.00")).quantize(Decimal("0.01"))
        items_sold = items_sold_by_seller.get(seller_id, Decimal("0"))
        points = (
            row["orders_count"] * 10
            + row["payments_count"] * 4
            + int(items_sold)
            + int(total_sales // Decimal("100"))
        )
        leaderboard.append(
            {
                "rank": index,
                "seller_id": seller_id,
                "seller_name": _staff_label(
                    row["order__created_by__first_name"],
                    row["order__created_by__last_name"],
                    row["order__created_by__email"],
                ),
                "seller_email": row["order__created_by__email"] or "",
                "orders_count": row["orders_count"],
                "payments_count": row["payments_count"],
                "items_sold": items_sold,
                "total_sales": total_sales,
                "points": points,
            }
        )

    top_items_raw = list(
        OrderLine.objects.filter(order_id__in=paid_order_ids, is_voided=False)
        .values("menu_item_id", "menu_item__name", "label")
        .annotate(quantity_sold=Sum("quantity"), revenue=Sum("line_total"), lines_count=Count("id"))
        .order_by("-quantity_sold", "-revenue", "label")[:10]
    )
    top_items = [
        {
            "item_name": row["menu_item__name"] or row["label"],
            "quantity_sold": row["quantity_sold"] or Decimal("0"),
            "revenue": (row["revenue"] or Decimal("0.00")).quantize(Decimal("0.01")),
            "lines_count": row["lines_count"],
        }
        for row in top_items_raw
    ]

    weekday_buckets: dict[int, dict[str, Decimal | int]] = defaultdict(
        lambda: {"payments_count": 0, "gross_sales": Decimal("0.00")}
    )
    for created_at, amount in payments_qs.values_list("created_at", "amount"):
        if business_zone is None:
            weekday = created_at.weekday()
        else:
            local = created_at.astimezone(business_zone)
            day = local.date() - timedelta(days=1) if local.hour < cutover_hour else local.date()
            weekday = day.weekday()
        weekday_buckets[weekday]["payments_count"] += 1
        weekday_buckets[weekday]["gross_sales"] += amount or Decimal("0.00")

    best_weekdays = []
    for weekday in range(7):
        bucket = weekday_buckets[weekday]
        best_weekdays.append(
            {
                "weekday": weekday,
                "label": WEEKDAY_LABELS[weekday],
                "payments_count": bucket["payments_count"],
                "gross_sales": (bucket["gross_sales"] or Decimal("0.00")).quantize(Decimal("0.01")),
            }
        )
    best_weekdays.sort(key=lambda row: (-row["gross_sales"], -row["payments_count"], row["weekday"]))

    top_seller = leaderboard[0] if leaderboard else None
    best_day = best_weekdays[0] if best_weekdays and best_weekdays[0]["payments_count"] else None

    net = (gross - ref_total).quantize(Decimal("0.01"))

    return {
        "payments_count": pay_count,
        "gross_sales": gross,
        "refunds_count": ref_count,
        "refunds_total": ref_total,
        "net_sales": net,
        "profitability": profitability,
        "by_payment_method": by_method,
        "by_outlet": by_outlet,
        "by_section": by_section,
        "leaderboard": leaderboard,
        "top_seller": top_seller,
        "top_items": top_items,
        "best_weekdays": best_weekdays,
        "best_day": best_day,
    }
