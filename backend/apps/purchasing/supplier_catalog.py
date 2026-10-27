"""Supplier-product planning helpers built from supplier references and receipt evidence."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .models import PurchaseReceiptLine, SupplierProductCode


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


def suggested_supplier_unit_cost(*, tenant_id, supplier_id, menu_item_id, product_package_id=None):
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
