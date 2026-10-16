"""Browser-accessible onboarding product import and no-payment checkout rehearsal."""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockMovement
from apps.pos.models import Order, Payment
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import TenantSetupProgress, TenantSettings
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def login_workspace(user, tenant):
    client = Client()
    assert client.login(username=user.email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(tenant.pk)
    session.save()
    return client


@pytest.mark.django_db
def test_import_screen_access_and_example_csv():
    a = _seed_tenant_bundle(
        name="CSV Screen", slug="csv-screen-test",
        user_email="csv-screen@example.test",
    )
    client = login_workspace(a["user"], a["tenant"])
    page = client.get(reverse("console-org-catalog-import"))
    assert page.status_code == 200, page.content[:400]
    assert b"Import products" in page.content
    sample = client.get(reverse("console-org-catalog-import") + "?sample=1")
    assert sample.status_code == 200
    assert sample["Content-Type"].startswith("text/csv")
    assert b"category,name,unit_price" in sample.content


@pytest.mark.django_db
def test_import_form_preview_and_atomic_save():
    from django.core.files.uploadedfile import SimpleUploadedFile
    a = _seed_tenant_bundle(
        name="CSV Web", slug="csv-web-import",
        user_email="csv-web@example.test",
    )
    client = login_workspace(a["user"], a["tenant"])
    url = reverse("console-org-catalog-import")
    raw = b"category,name,unit_price,sku\nDrinks,Sample Cola,2500.00,SAMPLE-COLA\n"
    preview = client.post(url, {
        "action": "preview",
        "file": SimpleUploadedFile("stock.csv", raw, content_type="text/csv"),
    })
    assert preview.status_code == 200, preview.content[:400]
    assert not MenuItem.objects.filter(tenant=a["tenant"], sku="SAMPLE-COLA").exists()
    created = client.post(url, {
        "action": "import",
        "file": SimpleUploadedFile("stock.csv", raw, content_type="text/csv"),
    })
    assert created.status_code == 302, created.content
    assert MenuItem.objects.filter(tenant=a["tenant"], sku="SAMPLE-COLA").count() == 1


@pytest.mark.django_db
def test_no_payment_practice_checkout_uses_configured_price():
    a = _seed_tenant_bundle(
        name="Practice Screen", slug="practice-screen",
        user_email="practice-screen@example.test",
    )
    settings = TenantSettings.objects.get(tenant=a["tenant"])
    settings.business_lines = ["bar"]
    settings.save(update_fields=["business_lines"])
    a["item"].unit_price = Decimal("10000.00")
    a["item"].tax_rate_percent = Decimal("18.00")
    a["item"].save(update_fields=["unit_price", "tax_rate_percent"])
    client = login_workspace(a["user"], a["tenant"])
    path = reverse("console-org-practice-sale")
    page = client.get(path)
    assert page.status_code == 200, page.content[:400]
    before_orders = Order.objects.filter(tenant=a["tenant"]).count()
    before_payments = Payment.objects.filter(tenant=a["tenant"]).count()
    before_movements = StockMovement.objects.filter(tenant=a["tenant"]).count()
    result = client.post(path, {
        "outlet": str(a["outlet"].pk),
        "menu_item": str(a["item"].pk),
        "quantity": "2",
    })
    assert result.status_code == 200, result.content[:700]
    ctx = result.context[-1] if isinstance(result.context, list) else result.context
    assert ctx["result"]["subtotal"] == Decimal("20000.00")
    assert ctx["result"]["tax"] == Decimal("3600.00")
    assert ctx["result"]["total"] == Decimal("23600.00")
    assert Order.objects.filter(tenant=a["tenant"]).count() == before_orders
    assert Payment.objects.filter(tenant=a["tenant"]).count() == before_payments
    assert StockMovement.objects.filter(tenant=a["tenant"]).count() == before_movements
    progress = TenantSetupProgress.objects.get(tenant=a["tenant"])
    assert progress.practice_sale_checked_at
    assert progress.practice_sale_checked_by_id == a["user"].pk


@pytest.mark.django_db
def test_restricted_business_does_not_expose_retail_import():
    a = _seed_tenant_bundle(
        name="Independent Hotel", slug="hotel-no-retail-import",
        user_email="hotel-import@example.test",
    )
    settings = TenantSettings.objects.get(tenant=a["tenant"])
    settings.business_lines = ["lodging"]
    settings.save(update_fields=["business_lines"])
    client = login_workspace(a["user"], a["tenant"])
    assert client.get(reverse("console-org-catalog-import")).status_code == 404
