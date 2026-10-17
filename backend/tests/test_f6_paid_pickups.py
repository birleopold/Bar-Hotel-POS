"""Paid pickup is a read-only handover record, not a second sale or layaway deposit."""
from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.customers.models import Customer
from apps.inventory.models import StockMovement
from apps.pos.models import Order, OrderStatus, RetailPickup
from apps.pos.services.pickups import register_paid_pickup, hand_over_paid_pickup
from apps.tenants.models import OutletType
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_paid_pickup_is_idempotent_and_does_not_create_stock_or_money():
    a = _seed_tenant_bundle(name="F6 Pickup", slug="f6-pickup", user_email="f6-pickup@test.local")
    a["outlet"].outlet_type = OutletType.RETAIL
    a["outlet"].save(update_fields=["outlet_type"])
    customer = Customer.objects.create(tenant=a["tenant"], name="Retail Pickup Person")
    order = Order.objects.create(tenant=a["tenant"], outlet=a["outlet"], customer=customer,
                                 status=OrderStatus.CLOSED, is_paid=True, currency="USD")
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
    assert not order.payments.exists()
    assert not order.refunds.exists()
    assert RetailPickup.objects.filter(order=order).count() == 1


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
