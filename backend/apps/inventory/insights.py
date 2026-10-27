"""Explainable inventory insights from posted stock movements and physical batches.

This is advisory-only. It does not place orders, amend stock balances or
invent supplier lead times. All calculations stay within explicit outlet scope.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING

from django.utils import timezone

from .batches import InventoryBatch
from .models import (
    StockMovement, StockReason, StockTransferRequest, StockTransferRequestStatus,
)
from apps.purchasing.models import PurchaseReceiptLine, SupplierProductCode
from apps.tenants.models import OutletType


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
            "outlet_type": balance.outlet.outlet_type,
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



def build_warehouse_replenishment_proposals(
    *,
    tenant,
    planning_rows,
    warehouse_balances,
):
    """Suggest warehouse-to-branch replenishment without posting stock.

    Existing inbound transfer requests reduce destination need. Approved
    warehouse requests that have not yet dispatched reserve source availability;
    dispatched stock is already absent from the warehouse StockBalance.
    """
    rows = list(planning_rows)
    warehouses = [
        balance for balance in warehouse_balances
        if balance.tenant_id == tenant.pk
        and balance.outlet.site.tenant_id == tenant.pk
        and balance.outlet.outlet_type == OutletType.WAREHOUSE
        and balance.quantity > 0
    ]
    if any(
        row.get("outlet_id") is None or row.get("menu_item_id") is None
        for row in rows
    ):
        raise ValueError("Planning rows must include outlet and product identity.")

    destination_ids = {
        row["outlet_id"] for row in rows
        if row.get("suggested_order") is not None
        and row["suggested_order"] > 0
    }
    product_ids = {row["menu_item_id"] for row in rows}
    warehouse_ids = {balance.outlet_id for balance in warehouses}

    inbound_open = defaultdict(lambda: Decimal("0"))
    source_reserved = defaultdict(lambda: Decimal("0"))
    if destination_ids and product_ids:
        open_requests = (
            StockTransferRequest.objects.filter(
                tenant=tenant,
                menu_item_id__in=product_ids,
                status__in=[
                    StockTransferRequestStatus.PENDING,
                    StockTransferRequestStatus.APPROVED,
                    StockTransferRequestStatus.DISPATCHED,
                ],
            )
            .select_related("transfer_receipt")
            .only(
                "from_outlet_id", "to_outlet_id", "menu_item_id",
                "status", "requested_quantity", "approved_quantity",
                "transfer_receipt__dispatched_quantity",
                "transfer_receipt__posted_quantity",
                "transfer_receipt__returned_quantity",
                "transfer_receipt__written_off_quantity",
            )
        )
        for request in open_requests.iterator():
            if request.to_outlet_id in destination_ids:
                if (
                    request.status == StockTransferRequestStatus.DISPATCHED
                    and request.transfer_receipt_id
                ):
                    quantity = max(
                        Decimal("0"),
                        request.transfer_receipt.outstanding_quantity,
                    )
                elif (
                    request.status == StockTransferRequestStatus.APPROVED
                    and request.approved_quantity is not None
                ):
                    quantity = request.approved_quantity
                else:
                    quantity = request.requested_quantity
                inbound_open[(request.to_outlet_id, request.menu_item_id)] += quantity
            if (
                request.from_outlet_id in warehouse_ids
                and request.status == StockTransferRequestStatus.APPROVED
                and request.approved_quantity is not None
            ):
                source_reserved[
                    (request.from_outlet_id, request.menu_item_id)
                ] += request.approved_quantity

    warehouse_by_product = defaultdict(list)
    remaining_source_available = {}
    for balance in warehouses:
        available = max(
            Decimal("0"),
            balance.quantity - source_reserved[
                (balance.outlet_id, balance.menu_item_id)
            ],
        )
        if available <= 0:
            continue
        key = (balance.outlet_id, balance.menu_item_id)
        remaining_source_available[key] = available
        warehouse_by_product[balance.menu_item_id].append(balance)

    proposals = []
    for row in rows:
        suggested = row.get("suggested_order")
        if (
            suggested is None
            or suggested <= 0
            or row.get("outlet_type") not in {
                OutletType.RETAIL, OutletType.SUPERMARKET,
            }
        ):
            continue
        destination_id = row["outlet_id"]
        item_id = row["menu_item_id"]
        inbound = inbound_open[(destination_id, item_id)]
        remaining_need = max(Decimal("0"), suggested - inbound).quantize(
            Decimal("0.001"), rounding=ROUND_CEILING
        )
        if remaining_need <= 0:
            continue

        candidates = sorted(
            warehouse_by_product.get(item_id, []),
            key=lambda balance: (
                -remaining_source_available.get(
                    (balance.outlet_id, item_id), Decimal("0")
                ),
                balance.outlet.name.casefold(),
                str(balance.outlet_id),
            ),
        )
        source_balance = next(
            (
                balance for balance in candidates
                if remaining_source_available.get(
                    (balance.outlet_id, item_id), Decimal("0")
                ) > 0
            ),
            None,
        )
        if source_balance is None:
            continue
        source_key = (source_balance.outlet_id, item_id)
        source_available = remaining_source_available[source_key]
        proposed = min(remaining_need, source_available).quantize(
            Decimal("0.001"), rounding=ROUND_CEILING
        )
        if proposed <= 0:
            continue
        remaining_source_available[source_key] = source_available - proposed
        proposals.append({
            "from_outlet_id": source_balance.outlet_id,
            "from_outlet": source_balance.outlet.name,
            "to_outlet_id": destination_id,
            "to_outlet": row["outlet"],
            "menu_item_id": item_id,
            "item": row["item"],
            "unit": row["unit"],
            "branch_on_hand": row["qty"],
            "suggested_need": suggested,
            "open_inbound": inbound.quantize(Decimal("0.001")),
            "remaining_need": remaining_need,
            "warehouse_on_hand": source_balance.quantity,
            "warehouse_available": source_available.quantize(Decimal("0.001")),
            "proposed_quantity": proposed,
            "unfilled_after_proposal": max(
                Decimal("0"), remaining_need - proposed
            ).quantize(Decimal("0.001")),
            "planning_basis": row["planning_basis"],
        })
    return proposals
