"""Import and first-run setup safety: reject bad files before writing any items."""
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import MenuCategory, MenuItem
from apps.console.catalog_import import (
    CatalogImportProblem, import_catalog_items, parse_catalog_csv,
)
from apps.console.setup_flow import (
    build_tenant_setup_state, set_tenant_setup_step_state,
)
from apps.pos.models import Workstation, WorkstationHardwareCheck
from apps.tenants.models import TenantSettings
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def file_of(text, name="items.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
def test_catalog_import_creates_categories_and_items_without_stock_postings():
    a = _seed_tenant_bundle(
        name="CSV Catalog", slug="csv-catalog-first-run",
        user_email="csv-catalog@example.test",
    )
    # An existing category should be reused without duplicates.
    contents = (
        "category,name,unit_price,sku,barcode,track_inventory,reorder_level,unit_of_measure,tax_rate_percent,description\n"
        "Beverages,Juice 300ml,2000.00,JUICE-300,6001112223334,yes,6,each,0,Pack\n"
        "Beverages,Tea Cup,3500.00,TEA-001,,no,,each,,Fresh\n"
    )
    rows = parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(contents))
    assert len(rows) == 2
    count = import_catalog_items(tenant=a["tenant"], rows=rows)
    assert count == 2
    juice = MenuItem.objects.get(tenant=a["tenant"], sku="JUICE-300")
    tea = MenuItem.objects.get(tenant=a["tenant"], sku="TEA-001")
    assert juice.category_id == tea.category_id
    assert juice.unit_price == 2000
    assert juice.reorder_level == 6
    assert not juice.outlet_links.exists()
    assert MenuCategory.objects.filter(tenant=a["tenant"], name="Beverages").count() == 1
    from apps.inventory.models import StockBalance, StockMovement
    assert not StockBalance.objects.filter(menu_item__in=[juice, tea]).exists()
    assert not StockMovement.objects.filter(menu_item__in=[juice, tea]).exists()


@pytest.mark.django_db
def test_csv_errors_are_atomic_with_no_first_row_writes():
    a = _seed_tenant_bundle(
        name="CSV Reject", slug="csv-reject-atomic",
        user_email="csv-reject@example.test",
    )
    original = MenuItem.objects.filter(tenant=a["tenant"]).count()
    content = (
        "category,name,unit_price,sku,track_inventory\n"
        "Drinks,Good Product,2500,P-001,yes\n"
        "Drinks,Invalid Price,not-a-price,P-002,no\n"
    )
    with pytest.raises(CatalogImportProblem, match="Row 3"):
        parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(content))
    assert MenuItem.objects.filter(tenant=a["tenant"]).count() == original
    assert not MenuCategory.objects.filter(tenant=a["tenant"], name="Drinks").exists()


@pytest.mark.django_db
def test_existing_sku_and_duplicate_barcodes_cannot_override_catalog():
    a = _seed_tenant_bundle(
        name="CSV Duplicates", slug="csv-duplicates",
        user_email="csv-duplicates@example.test",
    )
    a["item"].sku = "KEEP-1"
    a["item"].save(update_fields=["sku"])
    content = "category,name,unit_price,sku,barcode\nDrinks,Fraud,1500,keep-1,123\n"
    with pytest.raises(CatalogImportProblem, match="SKU already exists"):
        parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(content))
    repeated = (
        "category,name,unit_price,barcode\n"
        "Drinks,A,1500,ABC1\n"
        "Drinks,B,1500,abc1\n"
    )
    with pytest.raises(CatalogImportProblem, match="Barcode already exists"):
        parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(repeated))
    assert a["item"].sku == "KEEP-1"


@pytest.mark.django_db
def test_import_row_cap_and_decimal_safety():
    a = _seed_tenant_bundle(
        name="CSV Limits", slug="csv-import-limits",
        user_email="csv-limits@example.test",
    )
    oversized_rows = "category,name,unit_price\n" + "".join(
        f"Food,Item {i},2500\n" for i in range(1001)
    )
    with pytest.raises(CatalogImportProblem, match="at most 1,000"):
        parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(oversized_rows))
    bad_numbers = "category,name,unit_price\nFood,Fictional product,NaN\n"
    with pytest.raises(CatalogImportProblem):
        parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(bad_numbers))


@pytest.mark.django_db
def test_retail_catalog_import_accepts_over_250_rows_without_stock_movements():
    a = _seed_tenant_bundle(
        name="Large Grocery", slug="large-grocery-batch",
        user_email="large-grocery@example.test",
    )
    contents = "category,name,unit_price,sku,barcode\n" + "".join(
        f"Groceries,Item {index},1500.00,GROC-{index:04d},600{index:010d}\n"
        for index in range(300)
    )
    rows = parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(contents))
    assert len(rows) == 300
    assert import_catalog_items(tenant=a["tenant"], rows=rows) == 300
    assert MenuItem.objects.filter(tenant=a["tenant"], sku__startswith="GROC-").count() == 300


@pytest.mark.django_db
def test_required_setup_cannot_be_marked_finished_by_skipping():
    a = _seed_tenant_bundle(
        name="Required Setup", slug="required-setup-checks",
        user_email="setup-checks@example.test",
    )
    settings = TenantSettings.objects.get(tenant=a["tenant"])
    settings.business_lines = ["retail"]
    settings.save(update_fields=["business_lines"])
    first = build_tenant_setup_state(a["tenant"])
    assert any(step["key"] == "first_workstation" and not step["done"]
               for step in first["required_steps"])
    with pytest.raises(ValueError, match="cannot be skipped"):
        set_tenant_setup_step_state(a["tenant"], step_key="first_workstation", state="skipped")
    Workstation.objects.create(
        tenant=a["tenant"], outlet=a["outlet"],
        name="Main counter", code="main-counter",
    )
    later = build_tenant_setup_state(a["tenant"])
    assert any(step["key"] == "first_workstation" and step["done"]
               for step in later["required_steps"])
    assert any(step["key"] == "device_test" and not step["done"]
               for step in later["optional_steps"])


@pytest.mark.django_db
def test_catalog_import_is_tenant_scoped():
    a = _seed_tenant_bundle(
        name="Catalog A", slug="catalog-scoped-a",
        user_email="catalog-a@example.test",
    )
    b = _seed_tenant_bundle(
        name="Catalog B", slug="catalog-scoped-b",
        user_email="catalog-b@example.test",
    )
    rows = parse_catalog_csv(
        tenant=a["tenant"],
        uploaded=file_of("category,name,unit_price,sku\nGrocery,Bread,1500,BREAD-A\n"),
    )
    import_catalog_items(tenant=a["tenant"], rows=rows)
    assert MenuItem.objects.filter(tenant=a["tenant"], sku="BREAD-A").exists()
    assert not MenuItem.objects.filter(tenant=b["tenant"], sku="BREAD-A").exists()
