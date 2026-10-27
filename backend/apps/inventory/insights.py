"""Explainable inventory insights from posted stock movements and physical batches.

This is advisory-only. It does not place orders, amend stock balances or
invent supplier lead times. All calculations stay within explicit outlet scope.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING

from django.utils import timezone

from .batches import InventoryBatch
from .models import StockMovement, StockReason
from apps.purchasing.models import PurchaseReceiptLine, SupplierProductCode


def build_stock_intelligence(*, tenant, balances, safety_days=3, at=None):
    if not isinstance(safety_days, int) or not 0 <= safety_days <= 30:
        raise ValueError("Stock buffer must be between 0 and 30 days.")
    rows = list(balances)
    if any(row.tenant_id != tenant.pk or row.outlet.site.tenant_id != tenant.pk for row in rows):
        raise ValueError("Stock entries belong to another business.")
    if not rows:
        return []
    now = at or timezone.now()
    today = timezone.localdate(now)
    since_30 = now - timedelta(days=30)
    since_90 = now - timedelta(days=90)
    since_year = now - timedelta(days=365)
    pairs = {(row.outlet_id, row.menu_item_id) for row in rows}
    outlet_ids = {pair[0] for pair in pairs}
    product_ids = {pair[1] for pair in pairs}

    consumed = defaultdict(lambda: Decimal("0"))
    last_used = {}
    last_received = {}
    movements = StockMovement.objects.filter(
        tenant=tenant, outlet_id__in=outlet_ids, menu_item_id__in=product_ids,
        created_at__gte=since_year,
    ).values("outlet_id", "menu_item_id", "reason", "quantity_change", "created_at")
    for movement in movements.iterator():
        key = (movement["outlet_id"], movement["menu_item_id"])
        if key not in pairs:
            continue
        reason = movement["reason"]
        when = movement["created_at"]
        if reason == StockReason.RECEIVE and (
            key not in last_received or when > last_received[key]
        ):
            last_received[key] = when
        if reason in (StockReason.SALE, StockReason.RECIPE):
            if key not in last_used or when > last_used[key]:
                last_used[key] = when
            if when >= since_30 and movement["quantity_change"] < 0:
                consumed[key] -= movement["quantity_change"]

    aging = defaultdict(lambda: [Decimal("0")] * 4)
    allocated = defaultdict(lambda: Decimal("0"))
    batch_rows = InventoryBatch.objects.filter(
        tenant=tenant, outlet_id__in=outlet_ids, menu_item_id__in=product_ids,
        remaining_quantity__gt=0,
    ).values("outlet_id", "menu_item_id", "remaining_quantity", "received_at")
    for batch in batch_rows.iterator():
        key = (batch["outlet_id"], batch["menu_item_id"])
        if key not in pairs:
            continue
        units = batch["remaining_quantity"]
        age = max(0, (today - batch["received_at"]).days)
        bucket = 0 if age <= 30 else 1 if age <= 60 else 2 if age <= 90 else 3
        aging[key][bucket] += units
        allocated[key] += units

    preferred_suppliers = {
        row["menu_item_id"]: row
        for row in SupplierProductCode.objects.filter(
            tenant=tenant,
            menu_item_id__in=product_ids,
            product_package__isnull=True,
            is_active=True,
            is_preferred=True,
        )
        .values(
            "menu_item_id",
            "supplier_id",
            "supplier__name",
            "default_unit_cost",
            "code",
        )
    }

    lead_samples = defaultdict(list)
    deliveries = PurchaseReceiptLine.objects.filter(
        receipt__tenant=tenant,
        receipt__purchase_order__outlet_id__in=outlet_ids,
        purchase_order_line__menu_item_id__in=product_ids,
        receipt__created_at__gte=since_year,
    ).select_related("receipt__purchase_order", "purchase_order_line")
    for delivery in deliveries.iterator():
        po = delivery.receipt.purchase_order
        key = (po.outlet_id, delivery.purchase_order_line.menu_item_id)
        if key not in pairs:
            continue
        lead = (delivery.receipt.created_at - po.created_at).total_seconds() / 86400
        if lead >= 0:
            lead_samples[key].append(Decimal(str(lead)))

    results = []
    for balance in rows:
        key = (balance.outlet_id, balance.menu_item_id)
        qty = balance.quantity
        usage = consumed[key]
        daily = usage / Decimal("30")
        sample = lead_samples.get(key, [])
        lead_days = sum(sample, Decimal("0")) / len(sample) if sample else None
        target = (daily * (lead_days + Decimal(safety_days))
                  if lead_days is not None and daily > 0 else None)
        threshold = balance.menu_item.reorder_level
        if target is not None and threshold is not None:
            target = max(target, threshold)
        if target is None:
            target = threshold
        suggested = (max(Decimal("0"), target - qty).quantize(
            Decimal("0.001"), rounding=ROUND_CEILING
        ) if target is not None else None)
        available_days = qty / daily if daily > 0 else None
        unknown = qty - allocated[key]
        last_use = last_used.get(key)
        last_in = last_received.get(key)
        # Without a known long history, classify idle products as uncertain.
        inactive = (qty > 0 and last_in is not None
                    and last_in < since_90
                    and (last_use is None or last_use < since_90))
        movement_ratio = (usage / (usage + qty) * 100
                          if usage + qty > 0 else None)
        preferred = preferred_suppliers.get(balance.menu_item_id)
        results.append({
            "outlet_id": balance.outlet_id,
            "outlet": balance.outlet.name,
            "menu_item_id": balance.menu_item_id,
            "item": balance.menu_item.name,
            "preferred_supplier_id": preferred["supplier_id"] if preferred else None,
            "preferred_supplier": preferred["supplier__name"] if preferred else "",
            "preferred_supplier_code": preferred["code"] if preferred else "",
            "preferred_supplier_cost": preferred["default_unit_cost"] if preferred else None,
            "unit": balance.menu_item.get_unit_of_measure_display(),
            "qty": qty,
            "reorder_level": threshold,
            "age_0_30": aging[key][0],
            "age_31_60": aging[key][1],
            "age_61_90": aging[key][2],
            "age_over_90": aging[key][3],
            "unbatched_qty": max(Decimal("0"), unknown),
            "batch_discrepancy": unknown < 0,
            "last_received": last_in,
            "last_used": last_use,
            "units_consumed_30d": usage,
            "daily_usage": daily.quantize(Decimal("0.001")),
            "days_cover": available_days.quantize(Decimal("0.1")) if available_days is not None else None,
            "movement_ratio": movement_ratio.quantize(Decimal("0.1")) if movement_ratio is not None else None,
            "lead_days": lead_days.quantize(Decimal("0.1")) if lead_days is not None else None,
            "lead_samples": len(sample),
            "safety_days": safety_days,
            "suggested_order": suggested,
            "planning_basis": ("Observed lead time and movement history" if lead_days is not None and daily > 0
                               else "Configured reorder threshold" if threshold is not None
                               else "Insufficient history or reorder settings"),
            "low_stock": bool(threshold is not None and qty <= threshold),
            "inactive": inactive,
        })
    return results
