"""Supplier-product planning helpers built from supplier references and receipt evidence."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db.models import Q
from django.utils import timezone

from .models import (
    PurchaseReceiptLine,
    Supplier,
    SupplierPriceRecord,
    SupplierProductCode,
)


@dataclass(frozen=True)
class SupplierCostHistory:
    latest_unit_cost: Decimal | None
    previous_unit_cost: Decimal | None
    latest_received_at: object | None

    @property
    def change_amount(self) -> Decimal | None:
        if self.latest_unit_cost is None or self.previous_unit_cost is None:
            return None
        return (self.latest_unit_cost - self.previous_unit_cost).quantize(Decimal("0.01"))

    @property
    def change_percent(self) -> Decimal | None:
        if (
            self.latest_unit_cost is None
            or self.previous_unit_cost is None
            or self.previous_unit_cost == 0
        ):
            return None
        return (
            (self.latest_unit_cost - self.previous_unit_cost)
            / self.previous_unit_cost
            * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def supplier_product_reference(*, tenant_id, supplier_id, menu_item_id, product_package_id=None):
    qs = SupplierProductCode.objects.filter(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        menu_item_id=menu_item_id,
        is_active=True,
    ).select_related("supplier", "menu_item", "product_package")
    if product_package_id:
        package_row = qs.filter(product_package_id=product_package_id).order_by("created_at").first()
        if package_row is not None:
            return package_row
    return qs.filter(product_package__isnull=True).order_by("-is_preferred", "created_at").first()


def supplier_cost_histories(*, tenant_id, supplier_id, menu_item_ids) -> dict:
    wanted = {item_id for item_id in menu_item_ids if item_id}
    if not wanted:
        return {}
    buckets = {item_id: [] for item_id in wanted}
    rows = (
        PurchaseReceiptLine.objects.filter(
            receipt__tenant_id=tenant_id,
            receipt__purchase_order__supplier_id=supplier_id,
            purchase_order_line__menu_item_id__in=wanted,
            unit_cost_snapshot__isnull=False,
        )
        .order_by(
            "purchase_order_line__menu_item_id",
            "-receipt__created_at",
            "-created_at",
        )
        .values_list(
            "purchase_order_line__menu_item_id",
            "unit_cost_snapshot",
            "receipt__created_at",
        )
    )
    remaining = len(wanted)
    for menu_item_id, unit_cost, received_at in rows.iterator():
        bucket = buckets.get(menu_item_id)
        if bucket is None or len(bucket) >= 2:
            continue
        bucket.append((unit_cost, received_at))
        if len(bucket) == 2:
            remaining -= 1
            if remaining <= 0:
                break
    result = {}
    for menu_item_id, bucket in buckets.items():
        result[menu_item_id] = SupplierCostHistory(
            bucket[0][0] if bucket else None,
            bucket[1][0] if len(bucket) > 1 else None,
            bucket[0][1] if bucket else None,
        )
    return result


def supplier_cost_history(*, tenant_id, supplier_id, menu_item_id, limit=2) -> SupplierCostHistory:
    return supplier_cost_histories(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        menu_item_ids=[menu_item_id],
    ).get(menu_item_id, SupplierCostHistory(None, None, None))


def active_supplier_price(
    *,
    tenant_id,
    supplier_id,
    menu_item_id,
    ordered_quantity=None,
    product_package_id=None,
    as_of=None,
):
    day = as_of or timezone.localdate()
    qs = SupplierPriceRecord.objects.filter(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        menu_item_id=menu_item_id,
        is_active=True,
    ).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=day),
        Q(valid_until__isnull=True) | Q(valid_until__gte=day),
    )
    if ordered_quantity is not None:
        qty = Decimal(str(ordered_quantity))
        qs = qs.filter(minimum_quantity__lte=qty)
    else:
        qs = qs.filter(minimum_quantity__lte=Decimal("0.001"))

    ordering = ("-minimum_quantity", "-valid_from", "-created_at")
    if product_package_id:
        package_row = qs.filter(
            product_package_id=product_package_id
        ).order_by(*ordering).first()
        if package_row is not None:
            return package_row
    return qs.filter(product_package__isnull=True).order_by(*ordering).first()


def suggested_supplier_unit_cost(
    *,
    tenant_id,
    supplier_id,
    menu_item_id,
    product_package_id=None,
    ordered_quantity=None,
    as_of=None,
):
    price = active_supplier_price(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        menu_item_id=menu_item_id,
        product_package_id=product_package_id,
        ordered_quantity=ordered_quantity,
        as_of=as_of,
    )
    if price is not None:
        return price.unit_cost, "supplier_price_list"

    reference = supplier_product_reference(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        menu_item_id=menu_item_id,
        product_package_id=product_package_id,
    )
    if reference is not None and reference.default_unit_cost is not None:
        return reference.default_unit_cost, "supplier_default"
    history = supplier_cost_history(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        menu_item_id=menu_item_id,
    )
    if history.latest_unit_cost is not None:
        return history.latest_unit_cost, "latest_receipt"
    return None, ""


def supplier_purchase_options(
    *,
    tenant_id,
    menu_item_id,
    ordered_quantity,
    as_of=None,
) -> list[dict]:
    """Compare supplier planning evidence for one base product/quantity.

    This is intentionally not a vendor score. It exposes current price evidence,
    MOQ, lead time, preference and latest received cost separately.
    """
    day = as_of or timezone.localdate()
    try:
        qty = Decimal(str(ordered_quantity))
    except (InvalidOperation, TypeError, ValueError):
        qty = Decimal("0")
    if not qty.is_finite() or qty <= 0:
        return []

    references = list(
        SupplierProductCode.objects.filter(
            tenant_id=tenant_id,
            menu_item_id=menu_item_id,
            product_package__isnull=True,
            supplier__is_active=True,
            is_active=True,
        )
        .select_related("supplier")
        .order_by("supplier_id", "-is_preferred", "created_at")
    )
    prices = list(
        SupplierPriceRecord.objects.filter(
            tenant_id=tenant_id,
            menu_item_id=menu_item_id,
            product_package__isnull=True,
            supplier__is_active=True,
            is_active=True,
            minimum_quantity__lte=qty,
        )
        .filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=day),
            Q(valid_until__isnull=True) | Q(valid_until__gte=day),
        )
        .select_related("supplier")
        .order_by(
            "supplier_id",
            "-minimum_quantity",
            "-valid_from",
            "-created_at",
        )
    )
    receipt_base = PurchaseReceiptLine.objects.filter(
        receipt__tenant_id=tenant_id,
        purchase_order_line__menu_item_id=menu_item_id,
        receipt__purchase_order__supplier__is_active=True,
        unit_cost_snapshot__isnull=False,
    )
    receipt_supplier_ids = set(
        receipt_base.values_list(
            "receipt__purchase_order__supplier_id",
            flat=True,
        ).distinct()
    )

    reference_by_supplier = {}
    for row in references:
        reference_by_supplier.setdefault(row.supplier_id, row)
    price_by_supplier = {}
    for row in prices:
        price_by_supplier.setdefault(row.supplier_id, row)
    receipt_by_supplier = {}
    if receipt_supplier_ids:
        receipt_rows = (
            receipt_base
            .select_related("receipt__purchase_order__supplier")
            .order_by(
                "receipt__purchase_order__supplier_id",
                "-receipt__created_at",
                "-created_at",
            )
        )
        for row in receipt_rows.iterator(chunk_size=200):
            supplier_id = row.receipt.purchase_order.supplier_id
            receipt_by_supplier.setdefault(supplier_id, row)
            if len(receipt_by_supplier) >= len(receipt_supplier_ids):
                break

    supplier_ids = (
        set(reference_by_supplier)
        | set(price_by_supplier)
        | set(receipt_by_supplier)
    )
    if not supplier_ids:
        return []
    suppliers = {
        row.pk: row
        for row in Supplier.objects.filter(
            tenant_id=tenant_id,
            pk__in=supplier_ids,
            is_active=True,
        )
    }

    rows = []
    for supplier_id in supplier_ids:
        supplier = suppliers.get(supplier_id)
        if supplier is None:
            continue
        reference = reference_by_supplier.get(supplier_id)
        price = price_by_supplier.get(supplier_id)
        receipt_line = receipt_by_supplier.get(supplier_id)
        latest_received_cost = (
            receipt_line.unit_cost_snapshot
            if receipt_line is not None else None
        )
        latest_received_at = (
            receipt_line.receipt.created_at
            if receipt_line is not None else None
        )

        if price is not None:
            current_cost = price.unit_cost
            cost_source = "Effective price list"
            source_reference = price.source_reference
        elif reference is not None and reference.default_unit_cost is not None:
            current_cost = reference.default_unit_cost
            cost_source = "Supplier planning cost"
            source_reference = reference.code
        elif latest_received_cost is not None:
            current_cost = latest_received_cost
            cost_source = "Latest received cost"
            source_reference = ""
        else:
            current_cost = None
            cost_source = ""
            source_reference = ""

        minimum_order = (
            reference.minimum_order_quantity
            if reference is not None
            and reference.minimum_order_quantity is not None
            else None
        )
        eligible = not (
            minimum_order is not None and qty < minimum_order
        )
        rows.append({
            "supplier": supplier,
            "supplier_code": reference.code if reference else "",
            "preferred": bool(reference and reference.is_preferred),
            "minimum_order_quantity": minimum_order,
            "expected_lead_days": (
                reference.expected_lead_days if reference else None
            ),
            "current_cost": current_cost,
            "cost_source": cost_source,
            "source_reference": source_reference,
            "latest_received_cost": latest_received_cost,
            "latest_received_at": latest_received_at,
            "eligible": eligible,
            "is_lowest_cost": False,
        })

    known_eligible = [
        row for row in rows
        if row["eligible"] and row["current_cost"] is not None
    ]
    if known_eligible:
        lowest = min(row["current_cost"] for row in known_eligible)
        for row in rows:
            row["is_lowest_cost"] = bool(
                row["eligible"]
                and row["current_cost"] is not None
                and row["current_cost"] == lowest
            )

    rows.sort(key=lambda row: (
        not row["eligible"],
        row["current_cost"] is None,
        row["current_cost"] if row["current_cost"] is not None else Decimal("0"),
        not row["preferred"],
        row["supplier"].name.casefold(),
    ))
    return rows
