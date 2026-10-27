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
def test_incomplete_csv_rows_and_embedded_newlines_do_not_create_products():
    a = _seed_tenant_bundle(
        name="Malformed Grocery", slug="malformed-grocery-rows",
        user_email="malformed-grocery@example.test",
    )
    for content in (
        "category,name,unit_price,sku\nFood,Good Item,2500,G-1\nFood,No price\n",
        'category,name,unit_price,sku\nFood,"Two\nlines",2500,G-2\n',
    ):
        with pytest.raises(CatalogImportProblem):
            parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(content))
    assert not MenuItem.objects.filter(tenant=a["tenant"], sku__in=["G-1", "G-2"]).exists()


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

@pytest.mark.django_db
def test_catalog_export_is_tenant_scoped_and_available_from_owner_screen():
    import csv
    import io
    from django.test import RequestFactory
    from apps.console.views_catalog_import import OrgCatalogImportView
    a = _seed_tenant_bundle(
        name="Export A", slug="catalog-export-a",
        user_email="catalog-export-a@example.test",
    )
    b = _seed_tenant_bundle(
        name="Export B", slug="catalog-export-b",
        user_email="catalog-export-b@example.test",
    )
    MenuItem.objects.create(
        tenant=a["tenant"], category=a["item"].category,
        name="Export Sugar", unit_price="1000.00",
        sku="EXPORT-SUGAR", barcode="1234509876543",
    )
    request = RequestFactory().get("/console/org/menu/import/?export=1")
    request.tenant = a["tenant"]
    response = OrgCatalogImportView().get(request)
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    records = list(csv.DictReader(io.StringIO(response.content.decode("utf-8"))))
    assert any(row["sku"] == "EXPORT-SUGAR" for row in records)
    assert all(row["name"] != b["item"].name or row["sku"] != b["item"].sku for row in records)
    assert response["Cache-Control"] == "private, no-store"


def test_catalog_export_spreadsheet_formula_safety():
    from apps.console.views_catalog_import import _spreadsheet_safe
    assert _spreadsheet_safe("=1+1") == "'=1+1"
    assert _spreadsheet_safe("  @SUM(A1)") == "'  @SUM(A1)"
    assert _spreadsheet_safe("Sugar 1kg") == "Sugar 1kg"


@pytest.mark.django_db
def test_bulk_base_price_update_is_audited_and_does_not_rewrite_stock():
    from apps.console.catalog_import import parse_price_update_csv, apply_price_updates
    from apps.audit.models import AuditEvent
    a = _seed_tenant_bundle(
        name="Price Store", slug="price-store-update",
        user_email="price-store@example.test",
    )
    item = a["item"]
    item.sku = "PRICE-SUGAR"
    item.unit_price = "2500.00"
    item.save(update_fields=["sku", "unit_price"])
    rows = parse_price_update_csv(
        tenant=a["tenant"],
        uploaded=file_of("sku,old_price,new_price\nPRICE-SUGAR,2500.00,2600.00\n", "prices.csv"),
    )
    assert len(rows) == 1
    assert apply_price_updates(tenant=a["tenant"], rows=rows, user=a["user"]) == 1
    item.refresh_from_db()
    assert item.unit_price == 2600
    event = AuditEvent.objects.filter(
        tenant=a["tenant"], action="catalog.bulk_base_prices_updated",
    ).latest("created_at")
    assert event.payload["changes"][0]["before"] == "2500.00"
    assert event.payload["changes"][0]["after"] == "2600.00"
    from apps.inventory.models import StockMovement
    assert not StockMovement.objects.filter(tenant=a["tenant"], menu_item=item).exists()


@pytest.mark.django_db
def test_bulk_price_update_rejects_stale_cross_tenant_and_duplicate_rows_atomically():
    from apps.console.catalog_import import parse_price_update_csv, apply_price_updates
    a = _seed_tenant_bundle(
        name="Pricing A", slug="price-stale-a",
        user_email="price-stale-a@example.test",
    )
    b = _seed_tenant_bundle(
        name="Pricing B", slug="price-stale-b",
        user_email="price-stale-b@example.test",
    )
    item = a["item"]
    item.sku = "ONLY-STORE-A"
    item.unit_price = "1200.00"
    item.save(update_fields=["sku", "unit_price"])
    sheet = "sku,old_price,new_price\nONLY-STORE-A,1200.00,1300.00\n"
    with pytest.raises(CatalogImportProblem, match="not found"):
        parse_price_update_csv(tenant=b["tenant"], uploaded=file_of(sheet))
    with pytest.raises(CatalogImportProblem, match="unique"):
        parse_price_update_csv(tenant=a["tenant"], uploaded=file_of(sheet + sheet.split("\n")[1] + "\n"))
    rows = parse_price_update_csv(tenant=a["tenant"], uploaded=file_of(sheet))
    item.unit_price = "1250.00"
    item.save(update_fields=["unit_price"])
    with pytest.raises(CatalogImportProblem, match="Price changed"):
        apply_price_updates(tenant=a["tenant"], rows=rows, user=a["user"])
    item.refresh_from_db()
    assert item.unit_price == 1250


@pytest.mark.django_db
def test_bulk_price_update_rejects_ambiguous_existing_sku():
    from apps.console.catalog_import import parse_price_update_csv
    a = _seed_tenant_bundle(
        name="Ambiguous Prices", slug="ambiguous-price-sku",
        user_email="ambiguous-price-sku@example.test",
    )
    item = a["item"]
    item.sku = "SAME-SKU"
    item.unit_price = "1100.00"
    item.save(update_fields=["sku", "unit_price"])
    MenuItem.objects.create(
        tenant=a["tenant"], category=a["category"],
        name="Duplicate imported manually", sku="same-sku",
        unit_price="1100.00",
    )
    sheet = "sku,old_price,new_price\nSAME-SKU,1100.00,1200.00\n"
    with pytest.raises(CatalogImportProblem, match="Multiple products"):
        parse_price_update_csv(tenant=a["tenant"], uploaded=file_of(sheet))


def test_bulk_price_confirmation_is_exposed_on_catalog_page():
    import inspect
    from apps.console.views_catalog_import import OrgCatalogImportView
    from pathlib import Path
    template = Path(__file__).resolve().parents[1] / "apps" / "console" / "templates" / "console" / "org" / "catalog_import.html"
    assert 'name="confirm_price_changes"' in template.read_text(encoding="utf-8")
    assert 'self.request.POST.get("confirm_price_changes") != "yes"' in inspect.getsource(OrgCatalogImportView.form_valid)


@pytest.mark.django_db
def test_catalog_import_rejects_existing_quick_product_name_without_sku_collision():
    a = _seed_tenant_bundle(
        name="CSV Quick Name", slug="csv-quick-name-guard",
        user_email="csv-quick-name@example.test",
    )
    MenuItem.objects.create(
        tenant=a["tenant"], category=a["category"],
        name="New Kitchen Soap", sku="QUICK-123456",
        unit_price="5000.00", track_inventory=False,
    )
    csv_text = "category,name,unit_price,sku,barcode\nCleaning,new kitchen soap,5000.00,SOAP-02,\n"
    with pytest.raises(CatalogImportProblem, match="Product name already exists"):
        parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(csv_text))


@pytest.mark.django_db
def test_catalog_import_rechecks_names_at_commit_and_rejects_duplicate_csv_rows():
    a = _seed_tenant_bundle(
        name="CSV Name Race", slug="csv-name-race",
        user_email="csv-name-race@example.test",
    )
    csv_text = "category,name,unit_price,sku\nFood,New Arrival,800.00,A-01\n"
    prepared = parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(csv_text))
    MenuItem.objects.create(
        tenant=a["tenant"], category=a["category"],
        name="new arrival", sku="OTHER-01", unit_price="800.00",
    )
    before = MenuItem.objects.filter(tenant=a["tenant"]).count()
    with pytest.raises(CatalogImportProblem, match="Product name already exists"):
        import_catalog_items(tenant=a["tenant"], rows=prepared)
    assert MenuItem.objects.filter(tenant=a["tenant"]).count() == before

    duplicates = "category,name,unit_price,sku\nFood,Fresh Soap,900.00,F-01\nFood,fresh soap,900.00,F-02\n"
    with pytest.raises(CatalogImportProblem, match="Product name already exists"):
        parse_catalog_csv(tenant=a["tenant"], uploaded=file_of(duplicates))


def test_catalog_api_uses_same_tenant_lock_as_import_and_cashier():
    import inspect
    from apps.catalog.serializers import MenuItemSerializer
    src = inspect.getsource(MenuItemSerializer._save_with_tenant_lock)
    assert "Tenant.objects.select_for_update().get(pk=tenant_id)" in src
    assert "name__iexact=name" in src
    assert "Q(barcode__iexact=barcode)" in src
    assert "Q(sku__iexact=barcode)" in src
    assert "with transaction.atomic()" in src


@pytest.mark.django_db
def test_catalog_api_rejects_name_collision_with_quick_registered_item():
    from rest_framework.exceptions import ValidationError
    from rest_framework.test import APIRequestFactory
    from apps.catalog.serializers import MenuItemSerializer
    a = _seed_tenant_bundle(
        name="API Quick Collision", slug="api-quick-collision",
        user_email="api-quick-collision@example.test",
    )
    MenuItem.objects.create(
        tenant=a["tenant"], category=a["category"], name="New Arrival",
        sku="QUICK-API-01", unit_price="1000.00",
    )
    request = APIRequestFactory().post("/api/catalog/items/", {})
    request.tenant = a["tenant"]
    serializer = MenuItemSerializer(context={"request": request})
    with pytest.raises(ValidationError, match="name"):
        serializer.create({
            "tenant": a["tenant"], "category": a["category"],
            "name": "new arrival", "unit_price": "1000.00",
        })
