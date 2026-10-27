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

from apps.catalog.label_queue import queue_product_labels
from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    ProductAlternateCode,
    ProductPackage,
    RetailProductGroup,
    SupermarketSkuProfile,
    UnitOfMeasure,
)
from apps.tenants.models import Tenant

MAX_FILE_BYTES = 1024 * 1024
MAX_ITEMS = 1000
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


def _parse_bool(value: str, *, field_name="track_inventory"):
    value = value.strip().casefold()
    if value in ("", "no", "false", "0"):
        return False
    if value in ("yes", "true", "1"):
        return True
    raise ValueError(f"{field_name} must be yes or no.")


def parse_catalog_csv(*, tenant, uploaded):
    if getattr(uploaded, "size", 0) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a CSV smaller than 1 MB."])
    raw = uploaded.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a CSV smaller than 1 MB."])
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
        raise CatalogImportProblem(["Import at most 1,000 items per CSV."])

    existing_names = {
        value.casefold() for value in MenuItem.objects.filter(
            tenant=tenant, is_active=True,
        ).values_list("name", flat=True)
    }
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
    seen_skus = set()
    seen_barcodes = set()
    seen_names = set()
    rows = []
    errors = []
    valid_uom = {x.value for x in UnitOfMeasure}

    for row_idx, values in enumerate(records, 2):
        try:
            if not isinstance(values, dict) or None in values:
                raise ValueError("Use the supplied CSV columns; too many values were found.")
            # DictReader pads short rows with None. Never silently turn a
            # missing required cell into a valid empty field.
            if any(values.get(key) is None for key in REQUIRED):
                raise ValueError("CSV row is missing a required column value.")
            row = {str(key): str(value or "").strip()
                   for key, value in values.items()}
            if any("\x00" in value or "\r" in value or "\n" in value for value in row.values()):
                raise ValueError("Fields may not contain embedded control characters or line breaks.")
            cat = row.get("category", "")
            name = row.get("name", "")
            sku = row.get("sku", "")
            barcode = row.get("barcode", "")
            if not cat or len(cat) > 128 or not name or len(name) > 255:
                raise ValueError("Category (max 128) and name (max 255) are required.")
            if len(sku) > 64 or len(barcode) > 64:
                raise ValueError("SKU and barcode must each be 64 characters or fewer.")
            if name.casefold() in existing_names or name.casefold() in seen_names:
                raise ValueError("Product name already exists in this business or file.")
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
            seen_names.add(name.casefold())
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
        raise CatalogImportProblem(["Import between 1 and 1,000 items at once."])
    # Serialize concurrent imports for a business even if no menu items
    # exist yet; selecting only matching SKUs does not lock an empty table.
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    existing_names = {
        v.casefold() for v in MenuItem.objects.filter(
            tenant=tenant, is_active=True,
        ).values_list("name", flat=True)
    }
    seen_names = set()
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
        key = r["name"].casefold()
        if key in existing_names or key in seen_names:
            raise CatalogImportProblem(["Product name already exists: " + r["name"]])
        seen_names.add(key)
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
        queue_product_labels(
            menu_item=item,
            reason="new_product",
            user=None,
            note="Product created through catalogue CSV import.",
        )
        created += 1
    return created


def parse_price_update_csv(*, tenant, uploaded):
    """Preview price updates with an explicit expected current price.

    No data changes are made; each row must match one existing tenant SKU.
    Missing/duplicate SKUs and stale price snapshots fail the whole upload.
    """
    if getattr(uploaded, "size", 0) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a CSV smaller than 1 MB."])
    raw = uploaded.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a CSV smaller than 1 MB."])
    try:
        data = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogImportProblem(["Save the CSV as UTF-8."]) from exc
    try:
        reader = csv.DictReader(io.StringIO(data, newline=""), strict=True)
        headers = [h.strip().casefold() for h in (reader.fieldnames or []) if isinstance(h, str)]
        if len(headers) != 3 or set(headers) != {"sku", "old_price", "new_price"}:
            raise CatalogImportProblem(["Price CSV columns must be sku,old_price,new_price."])
        reader.fieldnames = headers
        records = list(reader)
    except csv.Error as exc:
        raise CatalogImportProblem(["Invalid price CSV quoting."]) from exc
    if not records or len(records) > MAX_ITEMS:
        raise CatalogImportProblem(["Submit between 1 and 1,000 price rows per file."])
    current, ambiguous = {}, set()
    for item in MenuItem.objects.filter(tenant=tenant).exclude(sku=""):
        key = item.sku.casefold()
        if key in current:
            ambiguous.add(key)
        current[key] = item
    issues, prepared, seen = [], [], set()
    for number, row in enumerate(records, 2):
        try:
            if None in row or any(row.get(k) is None for k in headers):
                raise ValueError("A column is missing or an extra value was supplied.")
            sku = row["sku"].strip()
            key = sku.casefold()
            if not sku or key in seen:
                raise ValueError("SKU must be present and unique within this file.")
            seen.add(key)
            if key in ambiguous:
                raise ValueError("Multiple products use this SKU; resolve duplicates first.")
            item = current.get(key)
            if item is None:
                raise ValueError("SKU not found in this business.")
            old = _decimal(row["old_price"], name="old_price", digits=12, places=2)
            new = _decimal(row["new_price"], name="new_price", digits=12, places=2)
            if item.unit_price != old:
                raise ValueError("Current price differs from old_price; export a fresh catalog.")
            prepared.append({
                "item_id": item.pk, "sku": item.sku, "name": item.name,
                "old_price": old, "new_price": new,
            })
        except ValueError as exc:
            issues.append(f"Row {number}: {exc}")
            if len(issues) >= 20:
                break
    if issues:
        raise CatalogImportProblem(issues)
    return prepared


PACKAGE_HEADERS = (
    "product_sku", "product_name", "package_name", "units_per_package",
    "barcode", "sku_alias", "sell_price", "is_sellable", "is_purchasable",
    "is_active",
)
PACKAGE_REQUIRED = ("product_sku", "package_name", "units_per_package")


def _package_reserved_codes(*, tenant):
    """All existing scanner identities that a new package code must not reuse."""
    from apps.inventory.models import InventorySerialUnit

    reserved = set()
    for sku, barcode in MenuItem.objects.filter(tenant=tenant).values_list("sku", "barcode"):
        if sku:
            reserved.add(str(sku).casefold())
        if barcode:
            reserved.add(str(barcode).casefold())
    for barcode, alias in ProductPackage.objects.filter(tenant=tenant).values_list("barcode", "sku_alias"):
        if barcode:
            reserved.add(str(barcode).casefold())
        if alias:
            reserved.add(str(alias).casefold())
    reserved.update(
        str(value).casefold()
        for value in RetailProductGroup.objects.filter(tenant=tenant)
        .exclude(code="")
        .values_list("code", flat=True)
    )
    reserved.update(
        str(value).casefold()
        for value in ProductAlternateCode.objects.filter(tenant=tenant)
        .exclude(code="")
        .values_list("code", flat=True)
    )
    reserved.update(
        str(value).casefold()
        for value in SupermarketSkuProfile.objects.filter(
            tenant=tenant, is_active=True,
        ).exclude(plu_code="").values_list("plu_code", flat=True)
    )
    reserved.update(
        str(value).casefold()
        for value in InventorySerialUnit.objects.filter(tenant=tenant)
        .exclude(serial_number="")
        .values_list("serial_number", flat=True)
    )
    return reserved


def parse_package_csv(*, tenant, uploaded):
    """Validate create-only package rows against existing concrete product SKUs."""
    if getattr(uploaded, "size", 0) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a package CSV smaller than 1 MB."])
    raw = uploaded.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a package CSV smaller than 1 MB."])
    try:
        data = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogImportProblem(["Save the package CSV as UTF-8."]) from exc
    try:
        reader = csv.DictReader(io.StringIO(data, newline=""), strict=True)
        headers = [h.strip().casefold() for h in (reader.fieldnames or []) if isinstance(h, str)]
        if len(headers) != len(set(headers)):
            raise CatalogImportProblem(["Package CSV column names must not repeat."])
        missing = [name for name in PACKAGE_REQUIRED if name not in headers]
        unknown = [name for name in headers if name not in PACKAGE_HEADERS]
        if missing or unknown:
            raise CatalogImportProblem([
                "Package CSV must include product_sku, package_name and units_per_package. "
                + (("Missing: " + ", ".join(missing) + ". ") if missing else "")
                + (("Unknown: " + ", ".join(unknown) + ".") if unknown else "")
            ])
        reader.fieldnames = headers
        records = list(reader)
    except csv.Error as exc:
        raise CatalogImportProblem(["The package CSV contains broken quoting or separators."]) from exc
    if not records or len(records) > MAX_ITEMS:
        raise CatalogImportProblem(["Import between 1 and 1,000 package rows per CSV."])

    products, ambiguous = {}, set()
    for item in MenuItem.objects.filter(tenant=tenant).exclude(sku=""):
        key = item.sku.casefold()
        if key in products:
            ambiguous.add(key)
        products[key] = item

    existing_names = {
        (package.menu_item_id, package.name.casefold())
        for package in ProductPackage.objects.filter(tenant=tenant).only(
            "menu_item_id", "name"
        )
    }
    reserved_codes = _package_reserved_codes(tenant=tenant)
    seen_names = set()
    seen_codes = set()
    prepared, errors = [], []

    for number, values in enumerate(records, 2):
        try:
            if not isinstance(values, dict) or None in values:
                raise ValueError("Use the supplied package CSV columns; too many values were found.")
            if any(values.get(key) is None for key in PACKAGE_REQUIRED):
                raise ValueError("Package row is missing a required column value.")
            row = {str(key): str(value or "").strip() for key, value in values.items()}
            if any("\x00" in value or "\r" in value or "\n" in value for value in row.values()):
                raise ValueError("Package fields may not contain embedded control characters or line breaks.")

            product_sku = row.get("product_sku", "")
            product_key = product_sku.casefold()
            if not product_sku or len(product_sku) > 64:
                raise ValueError("product_sku is required and must be 64 characters or fewer.")
            if product_key in ambiguous:
                raise ValueError("product_sku matches multiple products; resolve duplicate SKUs first.")
            item = products.get(product_key)
            if item is None:
                raise ValueError("product_sku was not found in this business.")

            package_name = row.get("package_name", "")
            if not package_name or len(package_name) > 96:
                raise ValueError("package_name is required and must be 96 characters or fewer.")
            name_key = (item.pk, package_name.casefold())
            if name_key in existing_names or name_key in seen_names:
                raise ValueError("This product already has a package with that name.")

            units = _decimal(
                row.get("units_per_package", ""),
                name="units_per_package", digits=14, places=3,
            )
            if units <= 0:
                raise ValueError("units_per_package must be greater than zero.")

            barcode = row.get("barcode", "")
            sku_alias = row.get("sku_alias", "")
            if len(barcode) > 64 or len(sku_alias) > 64:
                raise ValueError("barcode and sku_alias must each be 64 characters or fewer.")
            row_codes = [code.casefold() for code in (barcode, sku_alias) if code]
            if len(row_codes) != len(set(row_codes)):
                raise ValueError("barcode and sku_alias must be different when both are supplied.")
            for code in row_codes:
                if code in reserved_codes or code in seen_codes:
                    raise ValueError("A package barcode or alias already belongs to another scanner identity.")

            sell_price = (
                _decimal(row["sell_price"], name="sell_price", digits=12, places=2)
                if row.get("sell_price") else None
            )
            if sell_price is not None:
                per_base = sell_price / units
                if per_base != per_base.quantize(Decimal("0.01")):
                    raise ValueError(
                        "sell_price must divide exactly into a two-decimal base-unit price."
                    )

            prepared.append({
                "menu_item_id": item.pk,
                "product_sku": item.sku,
                "product_name": item.name,
                "package_name": package_name,
                "units_per_package": units,
                "barcode": barcode,
                "sku_alias": sku_alias,
                "sell_price": sell_price,
                "is_sellable": _parse_bool(
                    row.get("is_sellable") or "yes", field_name="is_sellable",
                ),
                "is_purchasable": _parse_bool(
                    row.get("is_purchasable") or "yes", field_name="is_purchasable",
                ),
                "is_active": _parse_bool(
                    row.get("is_active") or "yes", field_name="is_active",
                ),
            })
            seen_names.add(name_key)
            seen_codes.update(row_codes)
        except ValueError as exc:
            errors.append(f"Row {number}: {exc}")
            if len(errors) >= 20:
                break
    if errors:
        raise CatalogImportProblem(errors)
    return prepared


@transaction.atomic
def import_product_packages(*, tenant, rows):
    """Create validated package definitions only; never post inventory."""
    if not rows or len(rows) > MAX_ITEMS:
        raise CatalogImportProblem(["Import between 1 and 1,000 package rows."])
    Tenant.objects.select_for_update().get(pk=tenant.pk)

    ids = [row["menu_item_id"] for row in rows]
    products = {
        item.pk: item
        for item in MenuItem.objects.select_for_update().filter(
            tenant=tenant, pk__in=ids,
        )
    }
    reserved_codes = _package_reserved_codes(tenant=tenant)
    seen_names = set()
    seen_codes = set()

    for row in rows:
        item = products.get(row["menu_item_id"])
        if item is None or item.sku.casefold() != row["product_sku"].casefold():
            raise CatalogImportProblem(["Product identity changed; check the package file again."])
        if MenuItem.objects.filter(tenant=tenant, sku__iexact=item.sku).count() != 1:
            raise CatalogImportProblem([f"SKU {item.sku} is no longer unique in this business."])
        name_key = (item.pk, row["package_name"].casefold())
        if name_key in seen_names or ProductPackage.objects.filter(
            tenant=tenant, menu_item=item, name__iexact=row["package_name"],
        ).exists():
            raise CatalogImportProblem([f"{item.sku} already has package {row['package_name']}."])
        seen_names.add(name_key)
        codes = [code.casefold() for code in (row["barcode"], row["sku_alias"]) if code]
        if len(codes) != len(set(codes)):
            raise CatalogImportProblem([f"{item.sku} package barcode and alias must be different."])
        for code in codes:
            if code in reserved_codes or code in seen_codes:
                raise CatalogImportProblem([f"Scanner code collision while importing package for {item.sku}."])
        seen_codes.update(codes)

    created = 0
    for row in rows:
        item = products[row["menu_item_id"]]
        package = ProductPackage(
            tenant=tenant,
            menu_item=item,
            name=row["package_name"],
            units_per_package=row["units_per_package"],
            barcode=row["barcode"],
            sku_alias=row["sku_alias"],
            sell_price=row["sell_price"],
            is_sellable=row["is_sellable"],
            is_purchasable=row["is_purchasable"],
            is_active=row["is_active"],
        )
        try:
            package.full_clean()
        except ModelValidationError as exc:
            raise CatalogImportProblem([f"Package {item.sku} / {package.name}: {exc}"])
        package.save()
        created += 1
    return created


@transaction.atomic
def apply_price_updates(*, tenant, rows, user):
    """Atomically apply prechecked base price changes and audit each batch."""
    from apps.audit.services import log_audit

    if not rows or len(rows) > MAX_ITEMS:
        raise CatalogImportProblem(["Submit between 1 and 1,000 price rows."])
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    identifiers = [r["item_id"] for r in rows]
    if len(set(identifiers)) != len(identifiers):
        raise CatalogImportProblem(["Duplicate product in price update."])
    locked = {
        item.pk: item
        for item in MenuItem.objects.select_for_update().filter(
            tenant=tenant, pk__in=identifiers,
        )
    }
    for row in rows:
        item = locked.get(row["item_id"])
        if item is None or item.sku.casefold() != row["sku"].casefold():
            raise CatalogImportProblem(["Product identity changed; export and check again."])
        if MenuItem.objects.filter(tenant=tenant, sku__iexact=item.sku).count() != 1:
            raise CatalogImportProblem(["SKU is not unique in this business; resolve duplicates."])
        if item.unit_price != row["old_price"]:
            raise CatalogImportProblem([
                f"Price changed for {item.sku}; export and review current prices."
            ])
    changed = []
    for row in rows:
        item = locked[row["item_id"]]
        if item.unit_price == row["new_price"]:
            continue
        previous = item.unit_price
        item.unit_price = row["new_price"]
        item.save(update_fields=["unit_price", "updated_at"])
        queue_product_labels(
            menu_item=item,
            reason="price_change",
            user=user,
            note=f"Bulk base price changed from {previous} to {item.unit_price}.",
        )
        changed.append({
            "item_id": str(item.pk), "sku": item.sku,
            "before": str(previous), "after": str(item.unit_price),
        })
    log_audit(
        tenant_id=tenant.pk, user_id=user.pk,
        action="catalog.bulk_base_prices_updated",
        entity_type="menu_items", entity_id=str(tenant.pk),
        payload={"count": len(changed), "changes": changed},
    )
    return len(changed)
