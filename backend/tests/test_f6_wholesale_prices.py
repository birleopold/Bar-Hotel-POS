"""F6 wholesale prices: isolated retail tier setup and cashier settlement safety."""
from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.customers.models import Customer
from apps.pos.models import Order, OrderLine, WholesalePriceRule
from apps.pos.services.orders import adjust_open_order_line_quantity
from apps.pos.services.wholesale import apply_wholesale_tier, save_wholesale_tier
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import OutletType
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_manager_wholesale_checkout_needs_customer_qty_and_keeps_shelf_sales_unchanged():
    env = _seed_tenant_bundle(name="Wholesale Checkout", slug="f6-wh-sale", user_email="wh-sale@example.test")
    outlet, item, user = env["outlet"], env["item"], env["user"]
    outlet.outlet_type = OutletType.RETAIL
    outlet.save(update_fields=["outlet_type"])
    member = Membership.objects.get(user=user, tenant=env["tenant"])
    tier = save_wholesale_tier(
        tenant=env["tenant"], outlet=outlet, item_id=item.pk, quantity="6",
        price="3.50", user=user, membership=member,
    )
    assert tier.unit_price == Decimal("3.50")
    customer = Customer.objects.create(tenant=env["tenant"], name="Trade customer", created_by=user)
    sale = Order.objects.create(tenant=env["tenant"], outlet=outlet, customer=customer, currency="USD")
    line = OrderLine.objects.create(order=sale, menu_item=item, label=item.name, quantity=Decimal("8"),
                                    unit_price=Decimal("5"), line_total=Decimal("40"))
    chosen, replay = apply_wholesale_tier(order=sale, line_id=line.pk, membership=member, user=user)
    assert not replay
    assert chosen.unit_price == Decimal("3.50")
    sale.refresh_from_db()
    assert sale.total == Decimal("28")
    same, replay = apply_wholesale_tier(order=sale, line_id=line.pk, membership=member, user=user)
    assert replay and same.pk == line.pk
    changed = adjust_open_order_line_quantity(order=sale, line=line, quantity=Decimal("2"), user=user)
    assert changed.pricing_source == "menu"
    assert changed.unit_price == Decimal("5")
    sale.refresh_from_db()
    assert sale.total == Decimal("10")
    anonymous = Order.objects.create(tenant=env["tenant"], outlet=outlet, currency="USD")
    usual = OrderLine.objects.create(order=anonymous, menu_item=item, label=item.name,
                                     quantity=Decimal("8"), unit_price=Decimal("5"), line_total=Decimal("40"))
    with pytest.raises(ValidationError):
        apply_wholesale_tier(order=anonymous, line_id=usual.pk, membership=member, user=user)
    usual.refresh_from_db()
    assert usual.unit_price == Decimal("5")


@pytest.mark.django_db
def test_manager_applies_wholesale_price_inline_without_reloading_checkout():
    env = _seed_tenant_bundle(
        name="Wholesale Inline", slug="f6-wh-inline",
        user_email="wh-inline@example.test",
    )
    outlet, item, user = env["outlet"], env["item"], env["user"]
    outlet.outlet_type = OutletType.SUPERMARKET
    outlet.save(update_fields=["outlet_type"])
    member = Membership.objects.get(user=user, tenant=env["tenant"])
    save_wholesale_tier(
        tenant=env["tenant"], outlet=outlet, item_id=item.pk,
        quantity="6", price="3.50", user=user, membership=member,
    )
    customer = Customer.objects.create(
        tenant=env["tenant"], name="Trade account", created_by=user,
    )
    sale = Order.objects.create(
        tenant=env["tenant"], outlet=outlet, customer=customer,
        currency="USD", created_by=user,
    )
    line = OrderLine.objects.create(
        order=sale, menu_item=item, label=item.name, quantity=Decimal("8"),
        unit_price=Decimal("5"), line_total=Decimal("40"),
    )

    client = Client()
    assert client.login(username=user.email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(outlet.pk)
    session.save()
    url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})

    page = client.get(url)
    assert page.status_code == 200
    assert b"data-retail-wholesale-form" in page.content
    assert b"data-retail-wholesale-status" in page.content

    first = client.post(
        url,
        {"action": "apply_wholesale", "line_id": str(line.pk)},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert first.status_code == 200
    body = first.json()
    assert body["ok"] is True
    assert body["replay"] is False
    assert Decimal(body["unit_price"]) == Decimal("3.50")
    assert Decimal(body["line_total"]) == Decimal("28.00")
    assert Decimal(body["total"]) == Decimal("28.00")

    replay = client.post(
        url,
        {"action": "apply_wholesale", "line_id": str(line.pk)},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert replay.status_code == 200
    assert replay.json()["ok"] is True
    assert replay.json()["replay"] is True

    from pathlib import Path
    staff_root = Path(__file__).resolve().parents[1] / "apps" / "staff"
    controller = (staff_root / "static/staff/retail-counter-v2.js").read_text(
        encoding="utf-8"
    )
    assert '[data-retail-wholesale-form]' in controller
    assert "window.retailRefreshCheckout()" in controller
    assert "Never repeat a price mutation after an ambiguous response." in controller


@pytest.mark.django_db
def test_wholesale_rejects_non_manager_and_price_wrong_business():
    a = _seed_tenant_bundle(name="Wholesale A", slug="f6-wh-a", user_email="wh-a@example.test")
    b = _seed_tenant_bundle(name="Wholesale B", slug="f6-wh-b", user_email="wh-b@example.test")
    a["outlet"].outlet_type = OutletType.SUPERMARKET
    a["outlet"].save(update_fields=["outlet_type"])
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    with pytest.raises(ValidationError):
        save_wholesale_tier(tenant=a["tenant"], outlet=a["outlet"], item_id=b["item"].pk,
                             quantity="10", price="2", user=a["user"], membership=member)
    rule = save_wholesale_tier(tenant=a["tenant"], outlet=a["outlet"], item_id=a["item"].pk,
                               quantity="10", price="2", user=a["user"], membership=member)
    member.role = MembershipRole.STOREKEEPER
    member.save(update_fields=["role"])
    with pytest.raises(ValidationError):
        save_wholesale_tier(tenant=a["tenant"], outlet=a["outlet"], item_id=a["item"].pk,
                            quantity="10", price="1", user=a["user"], membership=member)
    rule.refresh_from_db()
    assert rule.unit_price == Decimal("2")


@pytest.mark.django_db
def test_wholesale_staff_screen_shows_tiers_only_in_scoped_retail_workspace():
    env = _seed_tenant_bundle(name="Wholesale Screen", slug="f6-wh-screen", user_email="wh-screen@example.test")
    env["outlet"].outlet_type = OutletType.RETAIL
    env["outlet"].save(update_fields=["outlet_type"])
    client = Client()
    assert client.login(username=env["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session.save()
    page = client.get(reverse("staff-wholesale-pricing"))
    assert page.status_code == 200, page.content
    assert b"Wholesale quantity prices" in page.content
