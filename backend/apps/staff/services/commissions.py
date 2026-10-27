from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Max, Q, Sum

from apps.accounts.models import SalesTarget
from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.pos.models import Order, OrderLine, Refund, SupermarketLineReturn


MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _line_net_revenue(order: Order, line: OrderLine) -> Decimal:
    gross = _money(line.line_total)
    subtotal = _money(order.subtotal)
    discount = _money(order.discount_amount)
    if gross <= 0 or subtotal <= 0 or discount <= 0:
        return gross
    allocated = (discount * gross / subtotal).quantize(MONEY, rounding=ROUND_HALF_UP)
    return max(ZERO, gross - min(gross, allocated))


def _mapped_return_reversal(line: OrderLine, *, start, end) -> Decimal:
    if not line.commission_amount_snapshot or line.quantity <= 0:
        return ZERO
    qty = (
        SupermarketLineReturn.objects.filter(
            order_line=line,
            created_at__gte=start,
            created_at__lte=end,
        ).aggregate(total=Sum("quantity"))["total"]
        or Decimal("0")
    )
    qty = min(Decimal(str(line.quantity)), Decimal(str(qty)))
    return (
        _money(line.commission_amount_snapshot) * qty / Decimal(str(line.quantity))
    ).quantize(MONEY, rounding=ROUND_HALF_UP)


def build_commission_report(
    *,
    tenant_id,
    date_from: date,
    date_to: date,
    allowed_outlet_ids,
    currency: str,
) -> dict:
    """Commission report from frozen sale snapshots plus refund evidence."""
    start, end = utc_day_range_inclusive(date_from, date_to)
    completed_order_ids = (
        Order.objects.filter(
            tenant_id=tenant_id,
            outlet_id__in=allowed_outlet_ids,
            is_paid=True,
        )
        .annotate(final_payment_at=Max("payments__created_at"))
        .filter(final_payment_at__gte=start, final_payment_at__lte=end)
        .values_list("id", flat=True)
    )
    lines = list(
        OrderLine.objects.filter(
            order_id__in=completed_order_ids,
            is_voided=False,
            commission_base_snapshot__isnull=False,
            sales_attributed_membership__isnull=False,
        )
        .select_related(
            "order",
            "order__outlet",
            "sales_attributed_membership__user",
        )
        .order_by("sales_attributed_membership_id", "order_id", "sort_order")
    )

    workers = defaultdict(lambda: {
        "membership_id": "",
        "worker": "",
        "gross_sales": ZERO,
        "gross_commission": ZERO,
        "mapped_return_reversal": ZERO,
        "allocated_refund_reversal": ZERO,
        "net_commission": ZERO,
        "line_count": 0,
    })
    order_lines = defaultdict(list)
    for line in lines:
        membership = line.sales_attributed_membership
        row = workers[str(membership.pk)]
        row["membership_id"] = str(membership.pk)
        row["worker"] = membership.user.get_full_name() or membership.user.email
        row["gross_sales"] += _money(line.commission_base_snapshot)
        row["gross_commission"] += _money(line.commission_amount_snapshot)
        row["line_count"] += 1
        reversal = _mapped_return_reversal(line, start=start, end=end)
        row["mapped_return_reversal"] += reversal
        order_lines[line.order_id].append(line)

    # Refunds that are already linked to physical line returns are handled above.
    # Other order-level refunds do not prove which item was refunded, so allocate
    # their commission reversal proportionally across commissionable line revenue.
    mapped_refund_ids = set(
        SupermarketLineReturn.objects.filter(
            refund__isnull=False,
            refund__created_at__gte=start,
            refund__created_at__lte=end,
            order__tenant_id=tenant_id,
            order__outlet_id__in=allowed_outlet_ids,
        ).values_list("refund_id", flat=True)
    )
    refunds = (
        Refund.objects.filter(
            tenant_id=tenant_id,
            order__outlet_id__in=allowed_outlet_ids,
            created_at__gte=start,
            created_at__lte=end,
        )
        .exclude(pk__in=mapped_refund_ids)
        .select_related("order")
    )
    unallocated_refund_amount = ZERO
    for refund in refunds:
        commission_lines = order_lines.get(refund.order_id, [])
        total_base = sum(
            (_money(line.commission_base_snapshot) for line in commission_lines),
            ZERO,
        )
        order_total = _money(refund.order.total)
        if not commission_lines or total_base <= 0 or order_total <= 0:
            unallocated_refund_amount += _money(refund.amount)
            continue
        refunded_share = min(Decimal("1"), _money(refund.amount) / order_total)
        for line in commission_lines:
            membership = line.sales_attributed_membership
            reversal = (
                _money(line.commission_amount_snapshot) * refunded_share
            ).quantize(MONEY, rounding=ROUND_HALF_UP)
            workers[str(membership.pk)]["allocated_refund_reversal"] += reversal

    rows = []
    for row in workers.values():
        for key in (
            "gross_sales",
            "gross_commission",
            "mapped_return_reversal",
            "allocated_refund_reversal",
        ):
            row[key] = _money(row[key])
        row["total_reversal"] = _money(
            row["mapped_return_reversal"] + row["allocated_refund_reversal"]
        )
        row["net_commission"] = _money(
            max(ZERO, row["gross_commission"] - row["total_reversal"])
        )
        rows.append(row)
    rows.sort(key=lambda row: (-row["net_commission"], row["worker"].lower()))

    targets = {
        str(target.membership_id): target
        for target in SalesTarget.objects.filter(
            tenant_id=tenant_id,
            membership_id__in=[row["membership_id"] for row in rows],
            period_start__lte=date_to,
            period_end__gte=date_from,
        ).select_related("membership__user")
    }
    for row in rows:
        target = targets.get(row["membership_id"])
        row["target_amount"] = _money(target.target_amount) if target else None
        if target and target.target_amount > 0:
            row["target_progress_percent"] = (
                row["gross_sales"] * Decimal("100") / target.target_amount
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        else:
            row["target_progress_percent"] = None

    return {
        "currency": (currency or "UGX").upper(),
        "workers": rows,
        "gross_commission": _money(sum((row["gross_commission"] for row in rows), ZERO)),
        "total_reversal": _money(sum((row["total_reversal"] for row in rows), ZERO)),
        "net_commission": _money(sum((row["net_commission"] for row in rows), ZERO)),
        "unallocated_refund_amount": _money(unallocated_refund_amount),
        "date_from": date_from,
        "date_to": date_to,
    }
