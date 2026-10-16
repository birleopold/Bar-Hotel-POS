"""Bounded, tenant-safe catalog CSV import for setup and later stock onboarding.

No stock balance is created: stock receipts must use the existing ledger.
All rows are parsed and checked before the first catalog change is committed.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction

from apps.catalog.models import MenuCategory, MenuItem, UnitOfMeasure

MAX_FILE_BYTES = 256 * 1024
MAX_ITEMS = 250
HEADERS = (
    "category", "name", "unit_price", "sku", "barcode", "track_inventory",
    "reorder_level", "unit_of_measure", "tax_rate_percent", "description",
)
REQUIRED = ("category", "name", "unit_price")


class CatalogImportProblem(ValueError):
    def __init__(self, issues):
        self.issues = list(issues)
        super().__init__("; ".join(self.issues[:8]))


def _decimal(raw: str, *, name: str, digits: int, places: int, maximum=None):
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f"{name} must be a number.")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be zero or greater.")
    if value.as_tuple().exponent < -places:
        raise ValueError(f"{name} supports at most {places} decimal places.")
    if len(value.as_tuple().digits) > digits or value >= Decimal(10) ** (digits - places):
        raise ValueError(f"{name} is too large.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} exceeds the allowed maximum.")
    return value


def _parse_bool(value: str):
    value = value.strip().casefold()
    if value in ("", "no", "false", "0"):
        return False
    if value in ("yes", "true", "1"):
        return True
    raise ValueError("track_inventory must be yes or no.")


def parse_catalog_csv(*, tenant, uploaded):
    if getattr(uploaded, "size", 0) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a CSV smaller than 256 KB."])
    raw = uploaded.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a CSV smaller than 256 KB."])
    try:
        data = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CatalogImportProblem(["Save the CSV as UTF-8 before uploading."])
    try:
        reader = csv.DictReader(io.StringIO(data, newline=""), strict=True)
        headers = [h.strip().casefold() for h in (reader.fieldnames or []) if isinstance(h, str)]
        if len(headers) != len(set(headers)):
            raise CatalogImportProblem(["CSV column names must not repeat."])
        missing = [name for name in REQUIRED if name not in headers]
        unknown = [name for name in headers if name not in HEADERS]
        if missing or unknown:
            raise CatalogImportProblem([
                "Columns must include category, name and unit_price. "
                + (("Missing: " + ", ".join(missing) + ". ") if missing else "")
                + (("Unknown: " + ", ".join(unknown) + ".") if unknown else "")
            ])
        reader.fieldnames = headers
        records = list(reader)
    except csv.Error:
        raise CatalogImportProblem(["The CSV contains broken quoting or separators."])
    if not records:
        raise CatalogImportProblem(["Add at least one item row."])
    if len(records) > MAX_ITEMS:
        raise CatalogImportProblem(["Import at most 250 items per CSV."])

    existing_skus = {
        value.casefold() for value in MenuItem.objects.filter(
            tenant=tenant,
        ).exclude(sku="").values_list("sku", flat=True)
    }
    existing_barcodes = {
        value.casefold() for value in MenuItem.objects.filter(
            tenant=tenant,
        ).exclude(barcode="").values_list("barcode", flat=True)
    }
    categories = {
        c.name.casefold(): c for c in MenuCategory.objects.filter(tenant=tenant)
    }
    seen_skus = set()
    seen_barcodes = set()
    rows = []
    errors = []
    valid_uom = {x.value for x in UnitOfMeasure}

    for row_idx, values in enumerate(records, 2):
        try:
            if not isinstance(values, dict) or None in values:
                raise ValueError("Use the supplied CSV columns; too many values were found.")
            row = {str(key): str(value or "").strip()
                   for key, value in values.items()}
            cat = row.get("category", "")
            name = row.get("name", "")
            sku = row.get("sku", "")
            barcode = row.get("barcode", "")
            if not cat or len(cat) > 128 or not name or len(name) > 255:
                raise ValueError("Category (max 128) and name (max 255) are required.")
            if len(sku) > 64 or len(barcode) > 64:
                raise ValueError("SKU and barcode must each be 64 characters or fewer.")
            if sku and (sku.casefold() in existing_skus or sku.casefold() in seen_skus):
                raise ValueError("SKU already exists in this business or file.")
            if barcode and (
                barcode.casefold() in existing_barcodes or barcode.casefold() in seen_barcodes
            ):
                raise ValueError("Barcode already exists in this business or file.")
            uom = row.get("unit_of_measure") or UnitOfMeasure.EACH.value
            if uom not in valid_uom:
                raise ValueError("unit_of_measure must be one of: " + ", ".join(sorted(valid_uom)))
            track_inventory = _parse_bool(row.get("track_inventory", ""))
            reorder_level = (
                _decimal(row["reorder_level"], name="reorder_level", digits=14, places=3)
                if row.get("reorder_level") else None
            )
            tax = (
                _decimal(row["tax_rate_percent"], name="tax_rate_percent",
                         digits=5, places=2, maximum=Decimal("100"))
                if row.get("tax_rate_percent") else None
            )
            description = row.get("description", "")
            if len(description) > 5000:
                raise ValueError("Description must be 5,000 characters or shorter.")
            prepared = {
                "category_name": cat, "name": name, "unit_price": _decimal(
                    row.get("unit_price", ""), name="unit_price", digits=12, places=2,
                ), "sku": sku, "barcode": barcode,
                "track_inventory": track_inventory,
                "reorder_level": reorder_level, "unit_of_measure": uom,
                "tax_rate_percent": tax, "description": description,
            }
            rows.append(prepared)
            if sku:
                seen_skus.add(sku.casefold())
            if barcode:
                seen_barcodes.add(barcode.casefold())
        except ValueError as exc:
            errors.append(f"Row {row_idx}: {exc}")
            if len(errors) >= 20:
                break
    if errors:
        raise CatalogImportProblem(errors)
    return rows


@transaction.atomic
def import_catalog_items(*, tenant, rows):
    """Create only new items; validate all before committing any rows."""
    if not rows or len(rows) > MAX_ITEMS:
        raise CatalogImportProblem(["Import between 1 and 250 items at once."])
    existing_skus = {
        v.casefold() for v in MenuItem.objects.select_for_update().filter(
            tenant=tenant,
        ).exclude(sku="").values_list("sku", flat=True)
    }
    existing_barcodes = {
        v.casefold() for v in MenuItem.objects.select_for_update().filter(
            tenant=tenant,
        ).exclude(barcode="").values_list("barcode", flat=True)
    }
    for r in rows:
        if r["sku"] and r["sku"].casefold() in existing_skus:
            raise CatalogImportProblem(["SKU already exists: " + r["sku"]])
        if r["barcode"] and r["barcode"].casefold() in existing_barcodes:
            raise CatalogImportProblem(["Barcode already exists: " + r["barcode"]])
    by_name = {
        c.name.casefold(): c for c in MenuCategory.objects.filter(tenant=tenant)
    }
    created = 0
    for r in rows:
        category_key = r["category_name"].casefold()
        category = by_name.get(category_key)
        if category is None:
            category = MenuCategory.objects.create(
                tenant=tenant, name=r["category_name"],
            )
            by_name[category_key] = category
        fields = {k: v for k, v in r.items() if k != "category_name"}
        item = MenuItem(tenant=tenant, category=category, **fields)
        try:
            item.full_clean()
        except ModelValidationError as exc:
            raise CatalogImportProblem([f"Item {item.name}: {exc}"])
        item.save()
        created += 1
    return created
