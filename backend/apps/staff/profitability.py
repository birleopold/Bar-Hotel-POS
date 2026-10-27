"""Historical merchandise profitability from immutable sale-time cost snapshots.

This report deliberately does not substitute current average cost for a sale
whose cost snapshot was incomplete. It reports coverage so management can tell
known gross profit from unknown cost exposure.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Max, Q
from apps.audit.models import AuditEvent, SensitiveActionApproval
from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.pos.models import Order, OrderLine, Refund, SupermarketLineReturn
from apps.tenants.models import OutletType, TenantSettings


MONEY = Decimal("0.01")
PERCENT = Decimal("0.1")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _historically_inventory_tracked(line: OrderLine) -> bool:
    if line.inventory_tracked_snapshot is not None:
        return bool(line.inventory_tracked_snapshot)
    return bool(
        line.menu_item_id
        and getattr(line.menu_item, "track_inventory", False)
    )


def _historical_item_name(line: OrderLine) -> str:
    label = (line.label or "").strip()
    if label:
        return label
    if line.menu_item_id:
        return line.menu_item.name
    return "Deleted merchandise"


def _historical_sku(line: OrderLine) -> str:
    snap = (line.merchandise_sku_snapshot or "").strip()
    if snap:
        return snap
    if line.menu_item_id:
        return line.menu_item.sku or ""
    return ""


def _historical_product_key(line: OrderLine):
    # Keep historical merchandise identities separate when a product is renamed
    # or its SKU changes. Current catalog edits must not rewrite old report rows.
    return (
        "item" if line.menu_item_id else "snapshot",
        str(line.menu_item_id or ""),
        _historical_sku(line).casefold(),
        _historical_item_name(line).casefold(),
    )


def _historical_category_name(line: OrderLine) -> str:
    snap = (line.merchandise_category_snapshot or "").strip()
    if snap:
        return snap
    if line.menu_item_id and getattr(line.menu_item, "category_id", None):
        return line.menu_item.category.name
    return "Uncategorized"


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
        )
        .filter(
            Q(inventory_tracked_snapshot=True)
            | Q(
                inventory_tracked_snapshot__isnull=True,
                menu_item__track_inventory=True,
            )
        )
        .select_related(
            "order", "order__outlet", "order__created_by",
            "menu_item", "menu_item__category",
        )
        .order_by("order_id", "sort_order", "created_at")
    )

    configured_margin_floor = (
        TenantSettings.objects.filter(tenant_id=tenant_id)
        .values_list("retail_min_margin_percent", flat=True)
        .first()
    )
    configured_margin_floor = (
        Decimal(str(configured_margin_floor))
        if configured_margin_floor is not None else None
    )

    totals = {
        "currency": currency,
        "configured_margin_floor_percent": configured_margin_floor,
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
    outlets = defaultdict(lambda: {
        "outlet_id": "",
        "outlet_name": "",
        **_blank_profit_row(),
    })
    retail_product_outlets = defaultdict(lambda: {
        "outlet_id": "",
        "outlet_name": "",
        "item_name": "",
        "sku": "",
        **_blank_profit_row(),
    })
    margin_breach_sales = []

    for line in line_qs.iterator(chunk_size=500):
        revenue = _line_net_revenue(line)
        trusted = (
            line.cost_basis_complete_snapshot
            and line.cost_unit_snapshot is not None
        )
        product_key = _historical_product_key(line)
        row = products[product_key]
        row["item_name"] = _historical_item_name(line)
        row["sku"] = _historical_sku(line)
        category_name = _historical_category_name(line)
        category_key = category_name.casefold()
        category_row = categories[category_key]
        category_row["category_name"] = category_name
        outlet_key = str(line.order.outlet_id)
        outlet_row = outlets[outlet_key]
        outlet_row["outlet_id"] = outlet_key
        outlet_row["outlet_name"] = line.order.outlet.name
        retail_product_row = None
        if line.order.outlet.outlet_type in {
            OutletType.RETAIL, OutletType.SUPERMARKET,
        }:
            retail_product_key = (product_key, outlet_key)
            retail_product_row = retail_product_outlets[retail_product_key]
            retail_product_row["outlet_id"] = outlet_key
            retail_product_row["outlet_name"] = line.order.outlet.name
            retail_product_row["item_name"] = _historical_item_name(line)
            retail_product_row["sku"] = _historical_sku(line)
        row["sale_revenue"] += revenue
        category_row["sale_revenue"] += revenue
        outlet_row["sale_revenue"] += revenue
        if retail_product_row is not None:
            retail_product_row["sale_revenue"] += revenue
        row["sale_units"] += line.quantity
        category_row["sale_units"] += line.quantity
        outlet_row["sale_units"] += line.quantity
        if retail_product_row is not None:
            retail_product_row["sale_units"] += line.quantity
        totals["sale_revenue"] += revenue
        totals["sale_units"] += line.quantity
        if trusted:
            cogs = (line.quantity * line.cost_unit_snapshot).quantize(
                MONEY, rounding=ROUND_HALF_UP
            )
            if (
                configured_margin_floor is not None
                and line.order.outlet.outlet_type in {
                    OutletType.RETAIL, OutletType.SUPERMARKET,
                }
            ):
                gross_profit = _money(revenue - cogs)
                margin_percent = (
                    (
                        gross_profit / revenue * Decimal("100")
                    ).quantize(PERCENT, rounding=ROUND_HALF_UP)
                    if revenue > 0 else None
                )
                if (
                    (margin_percent is not None and margin_percent < configured_margin_floor)
                    or (revenue <= 0 and cogs > 0)
                ):
                    target_gross_profit = _money(
                        revenue * configured_margin_floor / Decimal("100")
                    )
                    margin_shortfall = _money(
                        max(Decimal("0.00"), target_gross_profit - gross_profit)
                    )
                    margin_breach_sales.append({
                        "order_id": str(line.order_id),
                        "order_line_id": str(line.id),
                        "bill_reference": line.order.bill_reference or str(line.order_id),
                        "outlet_id": str(line.order.outlet_id),
                        "outlet_name": line.order.outlet.name,
                        "item_name": _historical_item_name(line),
                        "sku": _historical_sku(line),
                        "quantity": line.quantity,
                        "net_revenue": revenue,
                        "known_cogs": cogs,
                        "known_gross_profit": gross_profit,
                        "known_margin_percent": margin_percent,
                        "margin_floor_percent": configured_margin_floor,
                        "target_gross_profit": target_gross_profit,
                        "margin_shortfall": margin_shortfall,
                        "cashier_email": (
                            line.order.created_by.email
                            if line.order.created_by_id else ""
                        ),
                        "override_requester_email": "",
                        "override_approver_email": "",
                        "override_reason": "",
                        "override_approved_at": None,
                        "has_linked_margin_override": False,
                    })
            row["covered_revenue"] += revenue
            row["covered_units"] += line.quantity
            row["known_cogs"] += cogs
            category_row["covered_revenue"] += revenue
            category_row["covered_units"] += line.quantity
            category_row["known_cogs"] += cogs
            outlet_row["covered_revenue"] += revenue
            outlet_row["covered_units"] += line.quantity
            outlet_row["known_cogs"] += cogs
            if retail_product_row is not None:
                retail_product_row["covered_revenue"] += revenue
                retail_product_row["covered_units"] += line.quantity
                retail_product_row["known_cogs"] += cogs
            totals["covered_sale_revenue"] += revenue
            totals["covered_sale_units"] += line.quantity
            totals["known_sale_cogs"] += cogs
        else:
            row["incomplete_lines"] += 1
            category_row["incomplete_lines"] += 1
            outlet_row["incomplete_lines"] += 1
            if retail_product_row is not None:
                retail_product_row["incomplete_lines"] += 1
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
            "order_line__order__outlet",
            "order_line__menu_item",
            "order_line__menu_item__category",
        )
    )
    mapped_refund_ids = set()
    for returned in returns_qs.iterator(chunk_size=500):
        line = returned.order_line
        if not _historically_inventory_tracked(line):
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
        product_key = _historical_product_key(line)
        row = products[product_key]
        row["item_name"] = _historical_item_name(line)
        row["sku"] = _historical_sku(line)
        category_name = _historical_category_name(line)
        category_key = category_name.casefold()
        category_row = categories[category_key]
        category_row["category_name"] = category_name
        outlet_key = str(line.order.outlet_id)
        outlet_row = outlets[outlet_key]
        outlet_row["outlet_id"] = outlet_key
        outlet_row["outlet_name"] = line.order.outlet.name
        retail_product_row = None
        if line.order.outlet.outlet_type in {
            OutletType.RETAIL, OutletType.SUPERMARKET,
        }:
            retail_product_key = (product_key, outlet_key)
            retail_product_row = retail_product_outlets[retail_product_key]
            retail_product_row["outlet_id"] = outlet_key
            retail_product_row["outlet_name"] = line.order.outlet.name
            retail_product_row["item_name"] = _historical_item_name(line)
            retail_product_row["sku"] = _historical_sku(line)
        row["return_revenue"] += revenue_reversal
        category_row["return_revenue"] += revenue_reversal
        outlet_row["return_revenue"] += revenue_reversal
        if retail_product_row is not None:
            retail_product_row["return_revenue"] += revenue_reversal
        row["return_units"] += returned.quantity
        category_row["return_units"] += returned.quantity
        outlet_row["return_units"] += returned.quantity
        if retail_product_row is not None:
            retail_product_row["return_units"] += returned.quantity
        totals["return_revenue"] += revenue_reversal
        totals["return_units"] += returned.quantity
        if trusted:
            row["covered_return_revenue"] += revenue_reversal
            category_row["covered_return_revenue"] += revenue_reversal
            outlet_row["covered_return_revenue"] += revenue_reversal
            if retail_product_row is not None:
                retail_product_row["covered_return_revenue"] += revenue_reversal
            totals["covered_return_revenue"] += revenue_reversal
        if returned.restocked:
            if trusted:
                cogs_reversal = (
                    returned.quantity * line.cost_unit_snapshot
                ).quantize(MONEY, rounding=ROUND_HALF_UP)
                row["known_cogs_reversal"] += cogs_reversal
                category_row["known_cogs_reversal"] += cogs_reversal
                outlet_row["known_cogs_reversal"] += cogs_reversal
                if retail_product_row is not None:
                    retail_product_row["known_cogs_reversal"] += cogs_reversal
                totals["known_restock_cogs_reversal"] += cogs_reversal
            else:
                row["incomplete_return_lines"] += 1
                category_row["incomplete_return_lines"] += 1
                outlet_row["incomplete_return_lines"] += 1
                if retail_product_row is not None:
                    retail_product_row["incomplete_return_lines"] += 1
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
        )
        .filter(
            Q(inventory_tracked_snapshot=True)
            | Q(
                inventory_tracked_snapshot__isnull=True,
                menu_item__track_inventory=True,
            )
        )
        .values_list("order_id", flat=True)
        .distinct()
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
    outlet_rows = [_finalize_row(row) for row in outlets.values()]
    retail_product_rows = [
        _finalize_row(row) for row in retail_product_outlets.values()
    ]
    for row in outlet_rows:
        row["cost_coverage_percent"] = (
            (
                row["covered_revenue"] / row["sale_revenue"] * Decimal("100")
            ).quantize(PERCENT, rounding=ROUND_HALF_UP)
            if row["sale_revenue"] > 0 else Decimal("100.0")
        )
        row["profitability_complete"] = bool(
            row["incomplete_lines"] == 0
            and row["incomplete_return_lines"] == 0
        )
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
    outlet_rows.sort(
        key=lambda row: (
            -row["net_revenue"],
            row["outlet_name"].lower(),
        )
    )
    unknown_cost_exposure = [
        {
            "item_name": row["item_name"],
            "sku": row["sku"],
            "uncovered_net_revenue": row["uncovered_net_revenue"],
            "incomplete_lines": (
                row["incomplete_lines"] + row["incomplete_return_lines"]
            ),
        }
        for row in product_rows
        if row["uncovered_net_revenue"] > 0
        or row["incomplete_lines"] > 0
        or row["incomplete_return_lines"] > 0
    ]
    unknown_cost_exposure.sort(
        key=lambda row: (
            -row["uncovered_net_revenue"],
            -row["incomplete_lines"],
            row["item_name"].lower(),
        )
    )
    margin_exceptions = []
    if configured_margin_floor is not None:
        margin_exceptions = [
            {
                "outlet_id": row["outlet_id"],
                "outlet_name": row["outlet_name"],
                "item_name": row["item_name"],
                "sku": row["sku"],
                "covered_net_revenue": row["covered_net_revenue"],
                "known_net_cogs": row["known_net_cogs"],
                "known_gross_profit": row["known_gross_profit"],
                "known_margin_percent": row["known_margin_percent"],
                "margin_floor_percent": configured_margin_floor,
                "incomplete_cost_lines": (
                    row["incomplete_lines"] + row["incomplete_return_lines"]
                ),
            }
            for row in retail_product_rows
            if row["covered_net_revenue"] > 0
            and row["known_margin_percent"] is not None
            and row["known_margin_percent"] < configured_margin_floor
        ]
        margin_exceptions.sort(
            key=lambda row: (
                row["known_margin_percent"],
                -row["covered_net_revenue"],
                row["outlet_name"].lower(),
                row["item_name"].lower(),
            )
        )
    totals["products"] = product_rows[:25]
    totals["categories"] = category_rows[:25]
    totals["outlets"] = outlet_rows
    margin_breach_sales.sort(
        key=lambda row: (
            row["known_margin_percent"]
            if row["known_margin_percent"] is not None
            else Decimal("-999999"),
            row["known_gross_profit"],
            -row["net_revenue"],
            row["outlet_name"].lower(),
            row["item_name"].lower(),
        )
    )
    breach_line_ids = [
        row["order_line_id"] for row in margin_breach_sales
    ]
    if breach_line_ids:
        approval_by_line = {}
        approvals = (
            SensitiveActionApproval.objects.filter(
                tenant_id=tenant_id,
                action="discount",
                entity_type="order",
                entity_id__in=[row["order_id"] for row in margin_breach_sales],
                used_at__isnull=False,
            )
            .select_related("requester__user", "approver__user")
            .order_by("created_at")
        )
        breach_line_id_set = set(breach_line_ids)
        for approval in approvals:
            line_id = str((approval.intent_payload or {}).get("line_id") or "")
            if line_id in breach_line_id_set:
                approval_by_line[line_id] = approval

        override_event_by_line = {}
        events = (
            AuditEvent.objects.filter(
                tenant_id=tenant_id,
                action="order.line_discount_applied",
                entity_type="order_line",
                entity_id__in=breach_line_ids,
            )
            .order_by("created_at")
        )
        for event in events:
            payload = event.payload or {}
            if payload.get("margin_floor_overridden"):
                override_event_by_line[str(event.entity_id)] = event

        for row in margin_breach_sales:
            line_id = row["order_line_id"]
            approval = approval_by_line.get(line_id)
            event = override_event_by_line.get(line_id)
            if approval is not None and event is not None:
                row["has_linked_margin_override"] = True
                row["override_requester_email"] = approval.requester.user.email
                row["override_approver_email"] = approval.approver.user.email
                row["override_approved_at"] = approval.used_at
                row["override_reason"] = str(
                    (event.payload or {}).get("margin_override_reason") or ""
                ).strip()

    totals["unknown_cost_exposure"] = unknown_cost_exposure[:25]
    totals["margin_exceptions"] = margin_exceptions[:25]
    totals["margin_breach_sales"] = margin_breach_sales[:50]
    totals["margin_breach_sale_count"] = len(margin_breach_sales)
    totals["margin_breach_revenue"] = _money(sum(
        (row["net_revenue"] for row in margin_breach_sales),
        Decimal("0.00"),
    ))
    totals["margin_breach_gross_profit"] = _money(sum(
        (row["known_gross_profit"] for row in margin_breach_sales),
        Decimal("0.00"),
    ))
    totals["margin_breach_shortfall"] = _money(sum(
        (row["margin_shortfall"] for row in margin_breach_sales),
        Decimal("0.00"),
    ))

    # Evidence-based management actions. These are deliberately recommendations
    # only: they never rewrite historical cost, retail price, refunds or margin
    # settings. Unknown cost is kept separate from trusted-cost margin evidence.
    profitability_actions = []
    if (
        totals["uncovered_net_revenue"] > 0
        or totals["incomplete_sale_lines"] > 0
        or totals["incomplete_restock_return_lines"] > 0
    ):
        profitability_actions.append({
            "priority": "high",
            "kind": "cost_reconciliation",
            "title": "Reconcile missing merchandise cost",
            "detail": (
                f'{currency} {totals["uncovered_net_revenue"]} of net merchandise '
                "revenue is outside trusted-cost profit calculations. Reconcile "
                "cost from approved receiving, transfer or cost-bearing stock "
                "evidence before using it for margin decisions."
            ),
            "exposure_amount": totals["uncovered_net_revenue"],
            "affected_count": (
                totals["incomplete_sale_lines"]
                + totals["incomplete_restock_return_lines"]
            ),
        })
    if totals["margin_breach_sale_count"]:
        profitability_actions.append({
            "priority": "high",
            "kind": "margin_floor_review",
            "title": "Review sales below the retail margin floor",
            "detail": (
                f'{totals["margin_breach_sale_count"]} trusted-cost sale line(s) '
                f'missed the configured floor by {currency} '
                f'{totals["margin_breach_shortfall"]} of gross profit. Review '
                "discount approvals, selling price and supplier cost evidence; "
                "the report does not change prices automatically."
            ),
            "exposure_amount": totals["margin_breach_shortfall"],
            "affected_count": totals["margin_breach_sale_count"],
        })
    if totals["unmapped_refund_count"]:
        profitability_actions.append({
            "priority": "medium",
            "kind": "refund_attribution",
            "title": "Resolve unattributed merchandise refunds",
            "detail": (
                f'{totals["unmapped_refund_count"]} refund(s) worth {currency} '
                f'{totals["unmapped_refund_amount"]} cannot be tied to an exact '
                "returned merchandise line, so gross-profit coverage remains "
                "incomplete."
            ),
            "exposure_amount": totals["unmapped_refund_amount"],
            "affected_count": totals["unmapped_refund_count"],
        })
    if totals["foreign_currency_payment_count"]:
        profitability_actions.append({
            "priority": "medium",
            "kind": "currency_scope",
            "title": "Review historical foreign-currency sales separately",
            "detail": (
                f'{totals["foreign_currency_payment_count"]} completed sale(s) '
                f'are outside this {currency} profitability view. They remain '
                "excluded rather than being converted with a guessed exchange rate."
            ),
            "exposure_amount": Decimal("0.00"),
            "affected_count": totals["foreign_currency_payment_count"],
        })
    totals["profitability_actions"] = profitability_actions
    return totals
