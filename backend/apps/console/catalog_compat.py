"""Versioned external catalogue adapters.

External formats are translated into the project's canonical product CSV and
then validated by the existing catalogue importer. Adapters never post stock,
payments, or accounting balances.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .catalog_import import CatalogImportProblem, HEADERS, MAX_FILE_BYTES, MAX_ITEMS, parse_catalog_csv


@dataclass(frozen=True)
class CompatibilityReport:
    source: str
    adapter_version: str
    input_rows: int
    canonical_rows: int
    ignored_columns: tuple[str, ...]
    warnings: tuple[str, ...]


class _MemoryUpload:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.size = len(payload)

    def read(self, size=-1):
        if size is None or size < 0:
            return self._payload
        return self._payload[:size]


ADAPTERS = {
    "neutral": {
        "label": "This POS neutral CSV",
        "version": "2026-10-27",
    },
    "shopify": {
        "label": "Shopify product CSV",
        "version": "2026-10-27",
    },
    "square": {
        "label": "Square item library CSV",
        "version": "2026-10-27",
    },
    "quickbooks_online": {
        "label": "QuickBooks Online products/services CSV",
        "version": "2026-10-27",
    },
    "woocommerce": {
        "label": "WooCommerce product CSV",
        "version": "2026-10-27",
    },
}


def _read_csv(uploaded):
    if getattr(uploaded, "size", 0) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a CSV smaller than 1 MB."])
    raw = uploaded.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise CatalogImportProblem(["Upload a CSV smaller than 1 MB."])
    try:
        data = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogImportProblem(["Save the source export as UTF-8 CSV before uploading."]) from exc
    try:
        reader = csv.DictReader(io.StringIO(data, newline=""), strict=True)
        headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
        if not headers or len({h.casefold() for h in headers}) != len(headers):
            raise CatalogImportProblem(["The source CSV must have unique column headers."])
        records = list(reader)
    except csv.Error as exc:
        raise CatalogImportProblem(["The source CSV contains broken quoting or separators."]) from exc
    if not records:
        raise CatalogImportProblem(["The source export has no product rows."])
    if len(records) > MAX_ITEMS:
        raise CatalogImportProblem(["Import at most 1,000 source rows at a time."])
    return headers, records


def _first(row, *names):
    folded = {str(k or "").strip().casefold(): str(v or "").strip() for k, v in row.items()}
    for name in names:
        value = folded.get(name.casefold(), "")
        if value:
            return value
    return ""


def _money(value, default="0"):
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return default
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        return raw
    if amount < 0:
        return raw
    return format(amount.quantize(Decimal("0.01")), "f")


def _bool_text(value, default="no"):
    raw = str(value or "").strip().casefold()
    if raw in {"1", "true", "yes", "y", "active", "published", "instock", "in stock"}:
        return "yes"
    if raw in {"0", "false", "no", "n", "draft", "archived", "outofstock", "out of stock"}:
        return "no"
    return default


def _canonical_row(*, category, name, price, sku="", barcode="", track="no",
                   reorder="", uom="each", tax="", description=""):
    return {
        "category": (category or "Imported").strip()[:128],
        "name": (name or "").strip()[:255],
        "unit_price": _money(price),
        "sku": (sku or "").strip()[:64],
        "barcode": (barcode or "").strip()[:64],
        "track_inventory": track,
        "reorder_level": str(reorder or "").strip(),
        "unit_of_measure": uom or "each",
        "tax_rate_percent": str(tax or "").strip(),
        "description": (description or "").strip()[:5000],
    }


def _shopify(records):
    rows, warnings = [], []
    last_title_by_handle = {}
    for index, row in enumerate(records, start=2):
        handle = _first(row, "Handle")
        title = _first(row, "Title")
        if title and handle:
            last_title_by_handle[handle] = title
        base = title or last_title_by_handle.get(handle, "") or handle
        option_values = [
            _first(row, "Option1 Value"),
            _first(row, "Option2 Value"),
            _first(row, "Option3 Value"),
        ]
        option_values = [value for value in option_values if value and value.casefold() != "default title"]
        name = base
        if option_values:
            name = f"{base} - {' / '.join(option_values)}"
        sku = _first(row, "Variant SKU", "SKU")
        if not name:
            warnings.append(f"Row {index}: no product title/handle; row will fail canonical validation.")
        rows.append(_canonical_row(
            category=_first(row, "Type", "Product Category") or "Shopify import",
            name=name,
            price=_first(row, "Variant Price", "Price"),
            sku=sku,
            barcode=_first(row, "Variant Barcode", "Barcode"),
            track="yes" if _first(row, "Variant Inventory Tracker", "Inventory Tracker") else "no",
            description=_first(row, "Body (HTML)", "Body HTML", "Description"),
        ))
    return rows, warnings


def _square(records):
    rows = []
    for row in records:
        item = _first(row, "Item Name", "Token")
        variation = _first(row, "Variation Name")
        name = item if not variation or variation.casefold() in {"regular", "default"} else f"{item} - {variation}"
        rows.append(_canonical_row(
            category=_first(row, "Reporting Category", "Categories", "Category") or "Square import",
            name=name,
            price=_first(row, "Price", "Current Price", "Regular Price"),
            sku=_first(row, "SKU"),
            barcode=_first(row, "GTIN", "UPC", "Barcode"),
            track=_bool_text(_first(row, "Track Inventory", "Tracking Enabled"), default="no"),
            description=_first(row, "Description"),
        ))
    return rows, []


def _quickbooks(records):
    rows = []
    for row in records:
        full_name = _first(row, "Product/Service Name", "Name", "Product Service Name")
        pieces = [piece.strip() for piece in full_name.split(":") if piece.strip()]
        name = pieces[-1] if pieces else full_name
        category = ":".join(pieces[:-1]) if len(pieces) > 1 else _first(row, "Category")
        item_type = _first(row, "Type", "Product/Service Type")
        track = "yes" if item_type.casefold() in {"inventory", "inventory item"} else "no"
        rows.append(_canonical_row(
            category=category or "QuickBooks import",
            name=name,
            price=_first(row, "Sales Price/Rate", "Sales Price", "Price/Rate", "Price"),
            sku=_first(row, "SKU"),
            barcode=_first(row, "Barcode", "UPC"),
            track=track,
            description=_first(row, "Sales Description", "Description"),
        ))
    return rows, []


def _woocommerce(records):
    rows = []
    for row in records:
        name = _first(row, "Name")
        sku = _first(row, "SKU")
        rows.append(_canonical_row(
            category=_first(row, "Categories", "Category") or "WooCommerce import",
            name=name,
            price=_first(row, "Regular price", "Regular Price", "Price"),
            sku=sku,
            barcode=_first(row, "GTIN, UPC, EAN, or ISBN", "GTIN", "Barcode"),
            track=_bool_text(_first(row, "Stock status", "In stock?"), default="no"),
            description=_first(row, "Description", "Short description"),
        ))
    return rows, []


def _emit_canonical_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def parse_compatible_catalog_csv(*, tenant, uploaded, source):
    """Normalize one supported external product export into canonical rows."""
    source = (source or "neutral").strip()
    if source not in ADAPTERS:
        raise CatalogImportProblem(["Choose a supported source platform."])
    if source == "neutral":
        rows = parse_catalog_csv(tenant=tenant, uploaded=uploaded)
        return rows, CompatibilityReport(
            source=source,
            adapter_version=ADAPTERS[source]["version"],
            input_rows=len(rows),
            canonical_rows=len(rows),
            ignored_columns=(),
            warnings=(),
        )

    headers, records = _read_csv(uploaded)
    normalizers = {
        "shopify": _shopify,
        "square": _square,
        "quickbooks_online": _quickbooks,
        "woocommerce": _woocommerce,
    }
    canonical, warnings = normalizers[source](records)
    recognized = {
        "shopify": {
            "handle","title","body (html)","body html","description","vendor","type","product category",
            "option1 value","option2 value","option3 value","variant sku","sku","variant barcode","barcode",
            "variant price","price","variant inventory tracker","inventory tracker",
        },
        "square": {
            "item name","token","variation name","description","sku","gtin","upc","barcode",
            "price","current price","regular price","reporting category","categories","category",
            "track inventory","tracking enabled",
        },
        "quickbooks_online": {
            "product/service name","name","product service name","category","type","product/service type",
            "sales price/rate","sales price","price/rate","price","sku","barcode","upc",
            "sales description","description",
        },
        "woocommerce": {
            "name","sku","regular price","price","categories","category","description","short description",
            "gtin, upc, ean, or isbn","gtin","barcode","stock status","in stock?","type","published",
        },
    }[source]
    ignored = tuple(header for header in headers if header.casefold() not in recognized)
    rows = parse_catalog_csv(
        tenant=tenant,
        uploaded=_MemoryUpload(_emit_canonical_bytes(canonical)),
    )
    report = CompatibilityReport(
        source=source,
        adapter_version=ADAPTERS[source]["version"],
        input_rows=len(records),
        canonical_rows=len(rows),
        ignored_columns=ignored,
        warnings=tuple(warnings),
    )
    return rows, report
