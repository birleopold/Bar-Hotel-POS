from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Max

from apps.accounts.models import SalesTarget
from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.pos.models import Order, OrderLine, Refund, SupermarketLineReturn


MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _worker_row(workers, membership):
    key = str(membership.pk)
    row = workers[key]
    row["membership_id"] = key
    row["worker"] = membership.user.get_full_name() or membership.user.email
    return row


def build_commission_report(
    *,
    tenant_id,
    date_from: date,
    date_to: date,
    allowed_outlet_ids,
    currency: str,
) -> dict:
    """Frozen sale commissions plus return/refund adjustments for the period.

    Gross commission is recognized on the date of final settlement. Reversals
    are recognized when the return/refund occurs, even if the original sale was
    settled in an earlier reporting period.
    """
    start, end = utc_day_range_inclusive(date_from, date_to)
    workers = defaultdict(lambda: {
        "membership_id": "",
        "worker": "",
        "gross_sales": ZERO,
        "sales_reversal": ZERO,
        "net_sales": ZERO,
        "gross_commission": ZERO,
        "mapped_return_reversal": ZERO,
        "allocated_refund_reversal": ZERO,
        "total_reversal": ZERO,
        "net_commission": ZERO,
        "line_count": 0,
    })

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
    sale_lines = list(
        OrderLine.objects.filter(
            order_id__in=completed_order_ids,
            is_voided=False,
            commission_base_snapshot__isnull=False,
            sales_attributed_membership__isnull=False,
        )
        .select_related(
            "order",
            "sales_attributed_membership__user",
        )
        .order_by("sales_attributed_membership_id", "order_id", "sort_order")
    )
    for line in sale_lines:
        row = _worker_row(workers, line.sales_attributed_membership)
        row["gross_sales"] += _money(line.commission_base_snapshot)
        row["gross_commission"] += _money(line.commission_amount_snapshot)
        row["line_count"] += 1

    # Exact physical returns reverse the exact credited line, regardless of the
    # original sale date. Linked refund IDs are excluded from general refund
    # allocation below so the same customer refund cannot reverse commission twice.
    returns = list(
        SupermarketLineReturn.objects.filter(
            order__tenant_id=tenant_id,
            order__outlet_id__in=allowed_outlet_ids,
            created_at__gte=start,
            created_at__lte=end,
            order_line__sales_attributed_membership__isnull=False,
            order_line__commission_base_snapshot__isnull=False,
        )
        .select_related(
            "order_line",
            "order_line__sales_attributed_membership__user",
            "refund",
        )
        .order_by("created_at")
    )
    mapped_refund_ids = {
        item.refund_id for item in returns if item.refund_id is not None
    }
    for item in returns:
        line = item.order_line
        if line.quantity <= 0:
            continue
        fraction = min(
            Decimal("1"),
            Decimal(str(item.quantity)) / Decimal(str(line.quantity)),
        )
        row = _worker_row(workers, line.sales_attributed_membership)
        row["sales_reversal"] += (
            _money(line.commission_base_snapshot) * fraction
        ).quantize(MONEY, rounding=ROUND_HALF_UP)
        row["mapped_return_reversal"] += (
            _money(line.commission_amount_snapshot) * fraction
        ).quantize(MONEY, rounding=ROUND_HALF_UP)

    # A general refund identifies the sale but not a specific item. Allocate its
    # adjustment proportionally across that sale's frozen credited lines. This
    # is explicit allocation, not inferred product attribution.
    refunds = list(
        Refund.objects.filter(
            tenant_id=tenant_id,
            order__outlet_id__in=allowed_outlet_ids,
            created_at__gte=start,
            created_at__lte=end,
        )
        .exclude(pk__in=mapped_refund_ids)
        .select_related("order")
        .order_by("created_at")
    )
    refund_order_ids = {refund.order_id for refund in refunds}
    refund_lines = defaultdict(list)
    if refund_order_ids:
        for line in (
            OrderLine.objects.filter(
                order_id__in=refund_order_ids,
                is_voided=False,
                commission_base_snapshot__isnull=False,
                sales_attributed_membership__isnull=False,
            )
            .select_related("sales_attributed_membership__user")
            .order_by("order_id", "sort_order")
        ):
            refund_lines[line.order_id].append(line)

    unallocated_refund_amount = ZERO
    for refund in refunds:
        commission_lines = refund_lines.get(refund.order_id, [])
        order_total = _money(refund.order.total)
        if not commission_lines or order_total <= 0:
            unallocated_refund_amount += _money(refund.amount)
            continue
        refunded_share = min(Decimal("1"), _money(refund.amount) / order_total)
        for line in commission_lines:
            row = _worker_row(workers, line.sales_attributed_membership)
            row["sales_reversal"] += (
                _money(line.commission_base_snapshot) * refunded_share
            ).quantize(MONEY, rounding=ROUND_HALF_UP)
            row["allocated_refund_reversal"] += (
                _money(line.commission_amount_snapshot) * refunded_share
            ).quantize(MONEY, rounding=ROUND_HALF_UP)

    rows = []
    for row in workers.values():
        for key in (
            "gross_sales",
            "sales_reversal",
            "gross_commission",
            "mapped_return_reversal",
            "allocated_refund_reversal",
        ):
            row[key] = _money(row[key])
        row["net_sales"] = _money(row["gross_sales"] - row["sales_reversal"])
        row["total_reversal"] = _money(
            row["mapped_return_reversal"] + row["allocated_refund_reversal"]
        )
        # Reporting may be negative when this period contains a clawback from an
        # earlier sale. Payroll payment itself remains out of scope.
        row["net_commission"] = _money(
            row["gross_commission"] - row["total_reversal"]
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
                row["net_sales"] * Decimal("100") / target.target_amount
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        else:
            row["target_progress_percent"] = None

    return {
        "currency": (currency or "UGX").upper(),
        "workers": rows,
        "gross_sales": _money(sum((row["gross_sales"] for row in rows), ZERO)),
        "sales_reversal": _money(sum((row["sales_reversal"] for row in rows), ZERO)),
        "net_sales": _money(sum((row["net_sales"] for row in rows), ZERO)),
        "gross_commission": _money(sum((row["gross_commission"] for row in rows), ZERO)),
        "total_reversal": _money(sum((row["total_reversal"] for row in rows), ZERO)),
        "net_commission": _money(sum((row["net_commission"] for row in rows), ZERO)),
        "unallocated_refund_amount": _money(unallocated_refund_amount),
        "date_from": date_from,
        "date_to": date_to,
    }
