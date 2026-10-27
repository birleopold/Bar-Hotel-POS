"""Sales aggregates for staff HTML (same rules as ``SalesSummaryView``)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.pos.models import OrderLine, Payment, Refund


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
    ).select_related("order", "order__outlet", "shift", "shift__workstation")

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
    ).select_related("order", "shift", "shift__workstation")
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

    register_gross = defaultdict(lambda: {"count": 0, "amount": Decimal("0.00")})
    for payment in payments_qs:
        if payment.shift_id and payment.shift.workstation_id:
            key = str(payment.shift.workstation_id)
            label = payment.shift.workstation.name
            code = payment.shift.workstation.code
        elif payment.shift_id:
            key = f"section:{payment.order.outlet_id}"
            label = f"{payment.order.outlet.name} · Section register"
            code = ""
        else:
            key = "legacy"
            label = "Unattributed / legacy"
            code = ""
        bucket = register_gross[key]
        bucket["label"] = label
        bucket["code"] = code
        bucket["count"] += 1
        bucket["amount"] += payment.amount or Decimal("0.00")

    register_refunds = defaultdict(lambda: {"count": 0, "amount": Decimal("0.00")})
    for refund in refunds_qs:
        if refund.shift_id and refund.shift.workstation_id:
            key = str(refund.shift.workstation_id)
            label = refund.shift.workstation.name
            code = refund.shift.workstation.code
        elif refund.shift_id:
            key = f"section:{refund.order.outlet_id}"
            label = f"{refund.order.outlet.name} · Section register"
            code = ""
        else:
            key = "legacy"
            label = "Unattributed / legacy"
            code = ""
        bucket = register_refunds[key]
        bucket["label"] = label
        bucket["code"] = code
        bucket["count"] += 1
        bucket["amount"] += refund.amount or Decimal("0.00")

    by_register = []
    for key in sorted(
        set(register_gross) | set(register_refunds),
        key=lambda item: (
            register_gross.get(item, register_refunds.get(item, {})).get("label", "")
        ).lower(),
    ):
        gross_row = register_gross.get(key, {})
        refund_row = register_refunds.get(key, {})
        gross_amount = (gross_row.get("amount") or Decimal("0.00")).quantize(Decimal("0.01"))
        refund_amount = (refund_row.get("amount") or Decimal("0.00")).quantize(Decimal("0.01"))
        by_register.append({
            "register_key": key,
            "register_name": gross_row.get("label") or refund_row.get("label") or "Register",
            "register_code": gross_row.get("code") or refund_row.get("code") or "",
            "payments_count": gross_row.get("count", 0),
            "refunds_count": refund_row.get("count", 0),
            "gross_sales": gross_amount,
            "refunds_total": refund_amount,
            "net_sales": (gross_amount - refund_amount).quantize(Decimal("0.01")),
        })
    by_register.sort(
        key=lambda row: (-row["net_sales"], -row["gross_sales"], row["register_name"].lower())
    )

    hour_buckets = defaultdict(
        lambda: {
            "payments_count": 0,
            "refunds_count": 0,
            "gross_sales": Decimal("0.00"),
            "refunds_total": Decimal("0.00"),
        }
    )
    for created_at, amount in payments_qs.values_list("created_at", "amount"):
        local = (
            created_at.astimezone(business_zone)
            if business_zone is not None
            else timezone.localtime(created_at)
        )
        bucket = hour_buckets[local.hour]
        bucket["payments_count"] += 1
        bucket["gross_sales"] += amount or Decimal("0.00")
    for created_at, amount in refunds_qs.values_list("created_at", "amount"):
        local = (
            created_at.astimezone(business_zone)
            if business_zone is not None
            else timezone.localtime(created_at)
        )
        bucket = hour_buckets[local.hour]
        bucket["refunds_count"] += 1
        bucket["refunds_total"] += amount or Decimal("0.00")

    hourly_sales = []
    for hour in range(24):
        bucket = hour_buckets[hour]
        gross_amount = (bucket["gross_sales"] or Decimal("0.00")).quantize(Decimal("0.01"))
        refund_amount = (bucket["refunds_total"] or Decimal("0.00")).quantize(Decimal("0.01"))
        hourly_sales.append({
            "hour": hour,
            "label": f"{hour:02d}:00–{hour:02d}:59",
            "payments_count": bucket["payments_count"],
            "refunds_count": bucket["refunds_count"],
            "gross_sales": gross_amount,
            "refunds_total": refund_amount,
            "net_sales": (gross_amount - refund_amount).quantize(Decimal("0.01")),
        })

    paid_order_ids = list(payments_qs.values_list("order_id", flat=True).distinct())

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
        "by_payment_method": by_method,
        "by_outlet": by_outlet,
        "by_register": by_register,
        "hourly_sales": hourly_sales,
        "by_section": by_section,
        "leaderboard": leaderboard,
        "top_seller": top_seller,
        "top_items": top_items,
        "best_weekdays": best_weekdays,
        "best_day": best_day,
    }
