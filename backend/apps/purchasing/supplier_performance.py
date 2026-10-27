"""Evidence-based supplier performance summaries for purchasing screens."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from .models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SupplierProductCode,
    SupplierReturn,
)


def _percent(numerator: Decimal, denominator: Decimal):
    if denominator <= 0:
        return None
    return (
        numerator / denominator * Decimal("100")
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def supplier_performance_rows(*, tenant, suppliers, days=365, at=None) -> dict:
    supplier_list = list(suppliers)
    supplier_ids = {supplier.pk for supplier in supplier_list}
    if not supplier_ids:
        return {}
    now = at or timezone.now()
    today = timezone.localdate(now)
    since = now - timedelta(days=days)

    rows = {
        supplier_id: {
            "mapped_products": 0,
            "preferred_products": 0,
            "purchase_orders": 0,
            "delivery_count": 0,
            "lead_samples": 0,
            "average_lead_days": None,
            "on_time_samples": 0,
            "on_time_count": 0,
            "on_time_percent": None,
            "ordered_due_units": Decimal("0"),
            "received_due_units": Decimal("0"),
            "quantity_fulfilled_percent": None,
            "received_units": Decimal("0"),
            "returned_units": Decimal("0"),
            "return_rate_percent": None,
            "cost_increases": 0,
            "cost_decreases": 0,
            "cost_unchanged": 0,
        }
        for supplier_id in supplier_ids
    }

    relationships = (
        SupplierProductCode.objects.filter(
            tenant=tenant,
            supplier_id__in=supplier_ids,
            product_package__isnull=True,
            is_active=True,
        )
        .values("supplier_id", "menu_item_id", "is_preferred")
        .distinct()
    )
    seen_relationships = set()
    for relation in relationships.iterator():
        key = (relation["supplier_id"], relation["menu_item_id"])
        if key in seen_relationships:
            continue
        seen_relationships.add(key)
        summary = rows[relation["supplier_id"]]
        summary["mapped_products"] += 1
        summary["preferred_products"] += int(relation["is_preferred"])

    purchase_orders = list(
        PurchaseOrder.objects.filter(
            tenant=tenant,
            supplier_id__in=supplier_ids,
            created_at__gte=since,
        )
        .exclude(status=PurchaseOrderStatus.CANCELLED)
        .values("id", "supplier_id", "created_at", "expected_date", "status")
    )
    po_by_id = {po["id"]: po for po in purchase_orders}
    for po in purchase_orders:
        rows[po["supplier_id"]]["purchase_orders"] += 1

    po_ids = set(po_by_id)
    due_po_ids = {
        po["id"]
        for po in purchase_orders
        if po["status"] == PurchaseOrderStatus.RECEIVED
        or (po["expected_date"] is not None and po["expected_date"] <= today)
    }
    if po_ids:
        for line in (
            PurchaseOrderLine.objects.filter(purchase_order_id__in=po_ids)
            .values(
                "purchase_order_id",
                "quantity_ordered",
                "quantity_received",
            )
            .iterator()
        ):
            po = po_by_id[line["purchase_order_id"]]
            if line["purchase_order_id"] in due_po_ids:
                summary = rows[po["supplier_id"]]
                summary["ordered_due_units"] += line["quantity_ordered"]
                summary["received_due_units"] += line["quantity_received"]

    first_receipt = {}
    receipt_ids = set()
    if po_ids:
        receipts = (
            PurchaseReceipt.objects.filter(
                tenant=tenant,
                purchase_order_id__in=po_ids,
                created_at__gte=since,
            )
            .values("id", "purchase_order_id", "created_at")
            .order_by("purchase_order_id", "created_at", "id")
        )
        for receipt in receipts.iterator():
            receipt_ids.add(receipt["id"])
            po = po_by_id[receipt["purchase_order_id"]]
            rows[po["supplier_id"]]["delivery_count"] += 1
            first_receipt.setdefault(receipt["purchase_order_id"], receipt["created_at"])

    lead_totals = defaultdict(lambda: Decimal("0"))
    for po_id, po in po_by_id.items():
        first = first_receipt.get(po_id)
        if first is not None:
            lead_days = max(
                Decimal("0"),
                Decimal(str((first - po["created_at"]).total_seconds())) / Decimal("86400"),
            )
            lead_totals[po["supplier_id"]] += lead_days
            rows[po["supplier_id"]]["lead_samples"] += 1
        if po_id in due_po_ids and po["expected_date"] is not None:
            summary = rows[po["supplier_id"]]
            summary["on_time_samples"] += 1
            first_date = timezone.localtime(first).date() if first is not None else None
            summary["on_time_count"] += int(
                first_date is not None and first_date <= po["expected_date"]
            )

    if receipt_ids:
        for receipt_line in (
            PurchaseReceiptLine.objects.filter(receipt_id__in=receipt_ids)
            .values(
                "receipt__purchase_order__supplier_id",
                "quantity_received",
            )
            .iterator()
        ):
            rows[receipt_line["receipt__purchase_order__supplier_id"]][
                "received_units"
            ] += receipt_line["quantity_received"]

    returns = (
        SupplierReturn.objects.filter(
            tenant=tenant,
            purchase_order__supplier_id__in=supplier_ids,
            created_at__gte=since,
        )
        .values("purchase_order__supplier_id", "quantity")
    )
    for returned in returns.iterator():
        rows[returned["purchase_order__supplier_id"]]["returned_units"] += returned["quantity"]

    # Latest two received supplier costs per supplier/product, queried once.
    cost_buckets = defaultdict(list)
    cost_rows = (
        PurchaseReceiptLine.objects.filter(
            receipt__tenant=tenant,
            receipt__purchase_order__supplier_id__in=supplier_ids,
            receipt__created_at__gte=since,
            unit_cost_snapshot__isnull=False,
        )
        .order_by(
            "receipt__purchase_order__supplier_id",
            "purchase_order_line__menu_item_id",
            "-receipt__created_at",
            "-created_at",
        )
        .values_list(
            "receipt__purchase_order__supplier_id",
            "purchase_order_line__menu_item_id",
            "unit_cost_snapshot",
        )
    )
    for supplier_id, menu_item_id, unit_cost in cost_rows.iterator():
        bucket = cost_buckets[(supplier_id, menu_item_id)]
        if len(bucket) < 2:
            bucket.append(unit_cost)

    for (supplier_id, _menu_item_id), costs in cost_buckets.items():
        if len(costs) < 2:
            continue
        if costs[0] > costs[1]:
            rows[supplier_id]["cost_increases"] += 1
        elif costs[0] < costs[1]:
            rows[supplier_id]["cost_decreases"] += 1
        else:
            rows[supplier_id]["cost_unchanged"] += 1

    for supplier_id, summary in rows.items():
        if summary["lead_samples"]:
            summary["average_lead_days"] = (
                lead_totals[supplier_id] / summary["lead_samples"]
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        summary["on_time_percent"] = _percent(
            Decimal(summary["on_time_count"]),
            Decimal(summary["on_time_samples"]),
        )
        summary["quantity_fulfilled_percent"] = _percent(
            summary["received_due_units"],
            summary["ordered_due_units"],
        )
        if (
            summary["quantity_fulfilled_percent"] is not None
            and summary["quantity_fulfilled_percent"] > Decimal("100.0")
        ):
            summary["quantity_fulfilled_percent"] = Decimal("100.0")
        summary["return_rate_percent"] = _percent(
            summary["returned_units"],
            summary["received_units"],
        )
    return rows
