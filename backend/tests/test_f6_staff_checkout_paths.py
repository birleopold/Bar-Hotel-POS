"""F6 real server-rendered cashier and manager path smoke tests."""
from datetime import timedelta
from decimal import Decimal
import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.pos.models import Order, OrderLine, OrderStatus, Payment, PaymentMethod, WholesalePriceRule, RetailPickup
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY
from apps.tenants.models import OutletType
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def staff_client(env):
    client = Client()
    assert client.login(username=env["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(env["outlet"].pk)
    session.save()
    return client


@pytest.mark.django_db
def test_manager_can_configure_tier_then_apply_it_to_customer_order_screen():
    e = _seed_tenant_bundle(name="F6 Wholesale UI Post", slug="f6-wh-post", user_email="f6-wh-post@test.local")
    e["outlet"].outlet_type = OutletType.RETAIL
    e["outlet"].save(update_fields=["outlet_type"])
    customer = Customer.objects.create(tenant=e["tenant"], name="Verified Trade Customer", created_by=e["user"])
    sale = Order.objects.create(tenant=e["tenant"], outlet=e["outlet"], customer=customer, total=Decimal("40"))
    line = OrderLine.objects.create(order=sale, menu_item=e["item"], label=e["item"].name,
                                    quantity=Decimal("8"), unit_price=Decimal("5"), line_total=Decimal("40"))
    client = staff_client(e)
    url = reverse("staff-wholesale-pricing")
    configured = client.post(url, {"menu_item_id": str(e["item"].pk),
                                  "minimum_quantity": "6", "unit_price": "3.50",
                                  "is_active": "on"})
    assert configured.status_code == 302, configured.content
    assert WholesalePriceRule.objects.filter(outlet=e["outlet"], menu_item=e["item"]).exists()
    sale_url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
    assert client.get(sale_url).status_code == 200
    approved = client.post(sale_url, {"action": "apply_wholesale", "line_id": str(line.pk)})
    assert approved.status_code == 302, approved.content
    line.refresh_from_db()
    assert line.unit_price == Decimal("3.50")
    assert line.pricing_source == "wholesale"


@pytest.mark.django_db
def test_staff_can_schedule_and_hand_over_paid_retail_pickup_from_order_screen():
    e = _seed_tenant_bundle(name="F6 Pickup UI Post", slug="f6-pickup-post", user_email="f6-pickup-post@test.local")
    e["outlet"].outlet_type = OutletType.SUPERMARKET
    e["outlet"].save(update_fields=["outlet_type"])
    customer = Customer.objects.create(tenant=e["tenant"], name="Pickup Customer", created_by=e["user"])
    sale = Order.objects.create(tenant=e["tenant"], outlet=e["outlet"], customer=customer,
                                status=OrderStatus.CLOSED, is_paid=True, total=Decimal("10.00"), currency="USD")
    Payment.objects.create(tenant=e["tenant"], order=sale, amount=Decimal("10"),
                           method=PaymentMethod.CASH, idempotency_key="ui-pickup-recorded")
    client = staff_client(e)
    sale_url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
    assert client.get(sale_url).status_code == 200
    planned = client.post(sale_url, {"action": "schedule_paid_pickup",
                         "expected_on": (timezone.localdate() + timedelta(days=2)).isoformat(),
                         "note": "Collect from customer service"})
    assert planned.status_code == 302, planned.content
    pickup = RetailPickup.objects.get(order=sale)
    assert pickup.status == RetailPickup.Status.AWAITING
    handover = client.post(sale_url, {"action": "hand_over_paid_pickup",
                           "note": "Matched customer's order reference and handed over goods."})
    assert handover.status_code == 302, handover.content
    pickup.refresh_from_db()
    assert pickup.status == RetailPickup.Status.COLLECTED
    listed = client.get(reverse("staff-retail-pickups") + "?status=collected")
    assert listed.status_code == 200
    assert sale.bill_reference.encode() in listed.content
