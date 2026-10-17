"""F6 read-only register second-screen remains staff-session and outlet scoped."""
from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse

from apps.pos.models import Order, OrderLine
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import OutletType
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_customer_display_shows_basket_no_customer_contact_or_session_controls():
    env = _seed_tenant_bundle(name="Retail Display", slug="f6-display", user_email="f6-display@test.local")
    env["outlet"].outlet_type = OutletType.SUPERMARKET
    env["outlet"].save(update_fields=["outlet_type"])
    sale = Order.objects.create(tenant=env["tenant"], outlet=env["outlet"],
                                currency="USD", total=Decimal("30"), subtotal=Decimal("30"))
    OrderLine.objects.create(order=sale, menu_item=env["item"], label="Coffee",
                             quantity=Decimal("2"), unit_price=Decimal("15"), line_total=Decimal("30"))
    url = reverse("staff-retail-customer-display", kwargs={"order_id": sale.pk})
    anonymous = Client().get(url)
    assert anonymous.status_code in (301, 302, 403)
    client = Client()
    assert client.login(username=env["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session.save()
    page = client.get(url)
    assert page.status_code == 200, page.content
    assert b"Coffee" in page.content
    assert b"30.00" in page.content
    assert b"f6-display@test.local" not in page.content
    assert "no-store" in page["Cache-Control"]
    assert b"staff-nav" not in page.content
    assert client.post(url).status_code == 405


@pytest.mark.django_db
def test_customer_display_cannot_open_nonretail_outlet_or_other_business():
    a = _seed_tenant_bundle(name="F6 Display A", slug="f6-display-a", user_email="f6-display-a@test.local")
    b = _seed_tenant_bundle(name="F6 Display B", slug="f6-display-b", user_email="f6-display-b@test.local")
    a["outlet"].outlet_type = OutletType.RETAIL
    a["outlet"].save(update_fields=["outlet_type"])
    sale = Order.objects.create(tenant=b["tenant"], outlet=b["outlet"], currency="USD")
    client = Client()
    assert client.login(username=a["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(a["tenant"].pk)
    session.save()
    assert client.get(reverse("staff-retail-customer-display", kwargs={"order_id": sale.pk})).status_code == 404
