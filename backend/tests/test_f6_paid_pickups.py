"""Paid pickup is a read-only handover record, not a second sale or layaway deposit."""
from datetime import timedelta
import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.customers.models import Customer
from apps.inventory.models import StockMovement
from apps.pos.models import Order, OrderStatus, RetailPickup, Payment, PaymentMethod
from apps.pos.services.pickups import register_paid_pickup, hand_over_paid_pickup
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import OutletType
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_paid_pickup_is_idempotent_and_does_not_create_stock_or_money():
    a = _seed_tenant_bundle(name="F6 Pickup", slug="f6-pickup", user_email="f6-pickup@test.local")
    a["outlet"].outlet_type = OutletType.RETAIL
    a["outlet"].save(update_fields=["outlet_type"])
    customer = Customer.objects.create(tenant=a["tenant"], name="Retail Pickup Person")
    order = Order.objects.create(tenant=a["tenant"], outlet=a["outlet"], customer=customer,
                                 status=OrderStatus.CLOSED, is_paid=True, currency="USD", total=5)
    Payment.objects.create(tenant=a["tenant"], order=order, amount=5,
                           method=PaymentMethod.CASH, idempotency_key="pickup-paid-evidence")
    member = Membership.objects.get(user=a["user"], tenant=a["tenant"])
    date = timezone.localdate() + timedelta(days=2)
    args = dict(order=order, expected_on=date, note="Collect from service desk", user=a["user"], membership=member)
    first, repeated = register_paid_pickup(**args)
    assert not repeated
    again, repeated = register_paid_pickup(**args)
    assert repeated and again.pk == first.pk
    with pytest.raises(ValidationError):
        register_paid_pickup(**{**args, "expected_on": date + timedelta(days=1)})
    picked, repeated = hand_over_paid_pickup(
        pickup=first, user=a["user"], membership=member,
        note="Verified the customer's identity before handing over goods.",
    )
    assert not repeated and picked.status == RetailPickup.Status.COLLECTED
    again, repeated = hand_over_paid_pickup(
        pickup=first, user=a["user"], membership=member,
        note="Verified the customer's identity before handing over goods.",
    )
    assert repeated and again.pk == first.pk
    assert not StockMovement.objects.filter(order=order).exists()
    assert order.payments.count() == 1
    assert not order.refunds.exists()
    assert RetailPickup.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_paid_pickup_schedule_and_handover_update_checkout_inline():
    env = _seed_tenant_bundle(
        name="F6 Pickup Inline",
        slug="f6-pickup-inline",
        user_email="f6-pickup-inline@test.local",
    )
    env["outlet"].outlet_type = OutletType.SUPERMARKET
    env["outlet"].save(update_fields=["outlet_type"])
    customer = Customer.objects.create(
        tenant=env["tenant"],
        name="Inline Pickup Person",
        created_by=env["user"],
    )
    order = Order.objects.create(
        tenant=env["tenant"],
        outlet=env["outlet"],
        customer=customer,
        created_by=env["user"],
        status=OrderStatus.CLOSED,
        is_paid=True,
        currency="USD",
        total=5,
    )
    Payment.objects.create(
        tenant=env["tenant"],
        order=order,
        amount=5,
        method=PaymentMethod.CASH,
        idempotency_key="pickup-inline-paid",
    )
    client = Client()
    assert client.login(username=env["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(env["outlet"].pk)
    session.save()
    url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
    expected = timezone.localdate() + timedelta(days=3)

    page = client.get(url)
    assert page.status_code == 200
    assert b"data-retail-pickup-zone" in page.content
    assert b"data-retail-pickup-form" in page.content

    payload = {
        "action": "schedule_paid_pickup",
        "expected_on": expected.isoformat(),
        "note": "Hold at customer service desk",
    }
    first = client.post(
        url,
        payload,
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert first.json()["replay"] is False
    pickup = RetailPickup.objects.get(order=order)

    replay = client.post(
        url,
        payload,
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert replay.status_code == 200
    assert replay.json()["replay"] is True
    assert RetailPickup.objects.filter(order=order).count() == 1

    handover = client.post(
        url,
        {
            "action": "hand_over_paid_pickup",
            "note": "Verified customer ID and handed over sealed goods.",
        },
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert handover.status_code == 200
    assert handover.json()["ok"] is True
    assert handover.json()["pickup_status"] == RetailPickup.Status.COLLECTED
    pickup.refresh_from_db()
    assert pickup.status == RetailPickup.Status.COLLECTED
    assert order.payments.count() == 1
    assert not StockMovement.objects.filter(order=order).exists()

    staff_root = __import__("pathlib").Path(__file__).resolve().parents[1] / "apps" / "staff"
    controller = (staff_root / "static/staff/retail-counter-v2.js").read_text(
        encoding="utf-8"
    )
    assert '[data-retail-pickup-form]' in controller
    assert 'window.retailRefreshZone("[data-retail-pickup-zone]")' in controller
    assert "Never replay it." in controller


@pytest.mark.django_db
def test_pickup_requires_paid_customer_and_right_store_permissions():
    a = _seed_tenant_bundle(name="F6 Pickup Role", slug="f6-pickup-role", user_email="f6-pickup-role@test.local")
    a["outlet"].outlet_type = OutletType.SUPERMARKET
    a["outlet"].save(update_fields=["outlet_type"])
    member = Membership.objects.get(user=a["user"], tenant=a["tenant"])
    order = Order.objects.create(tenant=a["tenant"], outlet=a["outlet"], currency="USD")
    args = dict(order=order, expected_on=timezone.localdate(), note="Desk collection",
                user=a["user"], membership=member)
    with pytest.raises(ValidationError):
        register_paid_pickup(**args)
    member.role = MembershipRole.STOREKEEPER
    member.save(update_fields=["role"])
    customer = Customer.objects.create(tenant=a["tenant"], name="Retail Pickup Person")
    order.customer, order.is_paid, order.status = customer, True, OrderStatus.CLOSED
    order.save(update_fields=["customer", "is_paid", "status"])
    with pytest.raises(ValidationError):
        register_paid_pickup(**args)


def test_retail_pickup_handover_permission_is_not_lodging_dependent():
    from apps.staff.services.permissions import membership_can_confirm_retail_pickup
    from types import SimpleNamespace

    for role in (
        MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
    ):
        assert membership_can_confirm_retail_pickup(SimpleNamespace(is_active=True, role=role))
        assert not membership_can_confirm_retail_pickup(SimpleNamespace(is_active=False, role=role))
    for role in (MembershipRole.STOREKEEPER, MembershipRole.SERVER, MembershipRole.FRONT_DESK):
        assert not membership_can_confirm_retail_pickup(SimpleNamespace(is_active=True, role=role))
    assert not membership_can_confirm_retail_pickup(None)
