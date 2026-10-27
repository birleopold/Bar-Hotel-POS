import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from apps.catalog.models import MenuItem
from apps.console.catalog_compat import (
    compatibility_export_rows,
    parse_compatible_catalog_csv,
)
from apps.console.catalog_import import import_catalog_items
from apps.console.views_catalog_import import OrgCatalogImportView
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def upload(text, name="migration.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "source,content,expected_name,expected_sku,expected_price",
    [
        (
            "shopify",
            "Handle,Title,Body (HTML),Type,Option1 Value,Variant SKU,Variant Barcode,Variant Price,Variant Inventory Tracker\n"
            "tee,Classic Tee,Soft shirt,Clothing,Large,TEE-L,111222333,25000,shopify\n",
            "Classic Tee - Large", "TEE-L", "25000.00",
        ),
        (
            "square",
            "Item Name,Variation Name,Description,SKU,GTIN,Price,Reporting Category,Track Inventory\n"
            "Coffee,Large,Hot drink,COF-L,998877,8000,Drinks,Y\n",
            "Coffee - Large", "COF-L", "8000.00",
        ),
        (
            "quickbooks_online",
            "Product/Service Name,SKU,Sales Price/Rate,Type,Sales Description,Category\n"
            "Electronics:USB Cable,USB-1,12000,Inventory,Type C cable,Electronics\n",
            "USB Cable", "USB-1", "12000.00",
        ),
        (
            "woocommerce",
            "Type,SKU,Name,Published,Regular price,Categories,Description,GTIN, UPC, EAN, or ISBN\n"
            "simple,MUG-1,Office Mug,1,18000,Office,Ceramic mug,444555666\n",
            "Office Mug", "MUG-1", "18000.00",
        ),
    ],
)
def test_supported_external_catalogue_adapters_normalize_into_canonical_import(
    source, content, expected_name, expected_sku, expected_price
):
    bundle = _seed_tenant_bundle(
        name=f"Compat {source}",
        slug=f"compat-{source.replace('_', '-')}",
        user_email=f"compat-{source}@example.test",
    )
    rows, report = parse_compatible_catalog_csv(
        tenant=bundle["tenant"],
        uploaded=upload(content),
        source=source,
    )
    assert report.source == source
    assert report.input_rows == 1
    assert report.canonical_rows == 1
    assert rows[0]["name"] == expected_name
    assert rows[0]["sku"] == expected_sku
    assert str(rows[0]["unit_price"]) == expected_price
    assert import_catalog_items(tenant=bundle["tenant"], rows=rows) == 1
    assert MenuItem.objects.filter(
        tenant=bundle["tenant"], sku=expected_sku, name=expected_name,
    ).exists()


@pytest.mark.django_db
def test_shopify_variant_rows_become_unique_concrete_sellable_products():
    bundle = _seed_tenant_bundle(
        name="Shopify variants", slug="shopify-variants",
        user_email="shopify-variants@example.test",
    )
    content = (
        "Handle,Title,Type,Option1 Name,Option1 Value,Variant SKU,Variant Price\n"
        "shirt,Oxford Shirt,Clothing,Size,Small,OX-S,45000\n"
        "shirt,,Clothing,Size,Large,OX-L,47000\n"
    )
    rows, _ = parse_compatible_catalog_csv(
        tenant=bundle["tenant"], uploaded=upload(content), source="shopify",
    )
    assert [row["name"] for row in rows] == [
        "Oxford Shirt - Small", "Oxford Shirt - Large",
    ]
    assert [row["sku"] for row in rows] == ["OX-S", "OX-L"]


@pytest.mark.django_db
def test_compatibility_report_lists_unmapped_vendor_columns_instead_of_hiding_them():
    bundle = _seed_tenant_bundle(
        name="Compat report", slug="compat-report",
        user_email="compat-report@example.test",
    )
    content = (
        "Item Name,Variation Name,Description,SKU,Price,Reporting Category,Track Inventory,Vendor Secret\n"
        "Sugar,Regular,1kg,SUGAR-1,5000,Groceries,Y,ignored-value\n"
    )
    rows, report = parse_compatible_catalog_csv(
        tenant=bundle["tenant"], uploaded=upload(content), source="square",
    )
    assert len(rows) == 1
    assert report.ignored_columns == ("Vendor Secret",)


@pytest.mark.django_db
def test_external_import_still_rejects_existing_tenant_sku_atomically():
    bundle = _seed_tenant_bundle(
        name="Compat collision", slug="compat-collision",
        user_email="compat-collision@example.test",
    )
    bundle["item"].sku = "DUP-1"
    bundle["item"].save(update_fields=["sku"])
    content = (
        "Product/Service Name,SKU,Sales Price/Rate,Type\n"
        "Duplicate,DUP-1,1000,Inventory\n"
    )
    with pytest.raises(Exception, match="SKU already exists"):
        parse_compatible_catalog_csv(
            tenant=bundle["tenant"], uploaded=upload(content),
            source="quickbooks_online",
        )
    assert MenuItem.objects.filter(tenant=bundle["tenant"], sku="DUP-1").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "target,required_keys",
    [
        ("neutral", {"category", "name", "unit_price", "sku"}),
        ("shopify", {"Handle", "Title", "Variant SKU", "Variant Price"}),
        ("square", {"Item Name", "Variation Name", "SKU", "Price"}),
        ("quickbooks_online", {"Product/Service Name", "SKU", "Sales Price/Rate", "Type"}),
        ("woocommerce", {"Type", "SKU", "Name", "Regular price"}),
    ],
)
def test_outbound_compatibility_profiles_are_tenant_scoped(target, required_keys):
    a = _seed_tenant_bundle(
        name=f"Export {target}", slug=f"export-{target.replace('_', '-')}",
        user_email=f"export-{target}@example.test",
    )
    b = _seed_tenant_bundle(
        name=f"Other {target}", slug=f"other-{target.replace('_', '-')}",
        user_email=f"other-{target}@example.test",
    )
    a["item"].sku = "OWN-SKU"
    a["item"].save(update_fields=["sku"])
    b["item"].sku = "FOREIGN-SKU"
    b["item"].save(update_fields=["sku"])
    rows = list(compatibility_export_rows(tenant=a["tenant"], target=target))
    assert rows
    assert required_keys.issubset(rows[0].keys())
    text = repr(rows)
    assert "OWN-SKU" in text
    assert "FOREIGN-SKU" not in text


@pytest.mark.django_db
def test_owner_compatibility_export_is_spreadsheet_safe_and_no_store():
    bundle = _seed_tenant_bundle(
        name="Compat HTTP export", slug="compat-http-export",
        user_email="compat-http-export@example.test",
    )
    bundle["item"].name = "=Danger"
    bundle["item"].sku = "SAFE-SKU"
    bundle["item"].save(update_fields=["name", "sku"])
    request = RequestFactory().get(
        "/console/org/menu/import/?compat_export=neutral"
    )
    request.tenant = bundle["tenant"]
    request.user = bundle["user"]
    response = OrgCatalogImportView().get(request)
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8"))))
    own = next(row for row in rows if row["sku"] == "SAFE-SKU")
    assert own["name"].startswith("'=")
