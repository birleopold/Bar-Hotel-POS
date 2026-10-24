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
                                created_by=env["user"], total=Decimal("30"), subtotal=Decimal("30"))
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
    assert client.get(reverse("staff-order-detail", kwargs={"order_id": sale.pk})).status_code == 200
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


@pytest.mark.django_db
def test_customer_screen_follows_cashiers_new_basket_without_send_action():
    env = _seed_tenant_bundle(name="Queue Store", slug="f6-queue", user_email="f6-queue@test.local")
    env["outlet"].outlet_type = OutletType.SUPERMARKET
    env["outlet"].save(update_fields=["outlet_type"])
    first = Order.objects.create(tenant=env["tenant"], outlet=env["outlet"], created_by=env["user"])
    second = Order.objects.create(tenant=env["tenant"], outlet=env["outlet"], created_by=env["user"])
    client = Client()
    assert client.login(username=env["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session.save()
    assert client.get(reverse("staff-order-detail", kwargs={"order_id": second.pk})).status_code == 200
    first_url = reverse("staff-retail-customer-display", kwargs={"order_id": first.pk})
    page = client.get(first_url)
    assert page.status_code == 200
    assert str(second.pk).encode() in page.content
    current = page
    assert b"customer-display-live.js" in current.content
    assert b"data-customer-display-root" in current.content
    assert b'<meta http-equiv="refresh" content="4">' in current.content


@pytest.mark.django_db
def test_customer_screen_never_resurrects_paid_or_held_basket():
    env = _seed_tenant_bundle(name="No Old Receipts", slug="f6-no-old", user_email="f6-no-old@test.local")
    env["outlet"].outlet_type = OutletType.SUPERMARKET
    env["outlet"].save(update_fields=["outlet_type"])
    sale = Order.objects.create(tenant=env["tenant"], outlet=env["outlet"], created_by=env["user"])
    client = Client()
    assert client.login(username=env["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session.save()
    from apps.staff.views_customer_display import mark_customer_display_active
    mark_customer_display_active(sale, env["user"])
    url = reverse("staff-retail-customer-display", kwargs={"order_id": sale.pk})
    assert sale.bill_reference.encode() in client.get(url).content
    Order.objects.filter(pk=sale.pk).update(is_paid=True, status="closed")
    idle = client.get(url)
    assert idle.status_code == 200
    assert b"Welcome!" in idle.content
    assert sale.bill_reference.encode() not in idle.content
    next_sale = Order.objects.create(tenant=env["tenant"], outlet=env["outlet"], created_by=env["user"])
    assert client.get(reverse("staff-order-detail", kwargs={"order_id": next_sale.pk})).status_code == 200
    active = client.get(url)
    assert next_sale.bill_reference.encode() in active.content
    assert sale.bill_reference.encode() not in active.content
    hold = client.post(reverse("staff-order-detail", kwargs={"order_id": next_sale.pk}), {"action": "hold_order"})
    assert hold.status_code == 302
    idle = client.get(url)
    assert b"Welcome!" in idle.content
    assert next_sale.bill_reference.encode() not in idle.content
