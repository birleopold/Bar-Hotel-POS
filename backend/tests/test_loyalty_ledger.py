"""Tenant-safe loyalty points: manager-only manual ledger, replay and balance."""
import uuid
import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.customers.models import Customer, LoyaltyLedgerEntry
from apps.customers.loyalty import adjust_points, points_balance
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_manual_loyalty_points_are_idempotent_and_cannot_go_negative():
    a = _seed_tenant_bundle(name="Loyalty Check", slug="loyalty-check", user_email="loyalty-check@test.local")
    customer = Customer.objects.create(tenant=a["tenant"], name="Guest Lydia")
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    key = str(uuid.uuid4())
    params = dict(
        tenant=a["tenant"], customer_id=customer.pk, membership=member,
        user=a["user"], points=45, reason="Owner-issued welcome reward",
        source_key=key,
    )
    first, replay = adjust_points(**params)
    duplicate, repeated = adjust_points(**params)
    assert not replay and repeated
    assert first.pk == duplicate.pk
    assert points_balance(tenant=a["tenant"], customer=customer) == 45
    with pytest.raises(ValidationError):
        adjust_points(**{**params, "points": 90})
    with pytest.raises(ValidationError):
        adjust_points(**{**params, "points": -46, "source_key": str(uuid.uuid4())})
    negative, again = adjust_points(**{
        **params, "points": -15,
        "reason": "Correction of mistaken reward",
        "source_key": str(uuid.uuid4()),
    })
    assert negative.points == -15
    assert not again
    assert points_balance(tenant=a["tenant"], customer=customer) == 30
    assert LoyaltyLedgerEntry.objects.filter(customer=customer).count() == 2


@pytest.mark.django_db
def test_cross_tenant_and_staff_manual_loyalty_are_rejected():
    a = _seed_tenant_bundle(name="Customer East", slug="cust-east", user_email="cust-east@test.local")
    b = _seed_tenant_bundle(name="Customer West", slug="cust-west", user_email="cust-west@test.local")
    foreign_customer = Customer.objects.create(tenant=b["tenant"], name="Guest George")
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    params = dict(
        tenant=a["tenant"], customer_id=foreign_customer.pk,
        membership=member, user=a["user"], points=10,
        reason="Authorized customer reward", source_key=str(uuid.uuid4()),
    )
    with pytest.raises(ValidationError):
        adjust_points(**params)
    member.role = MembershipRole.SERVER
    member.save(update_fields=["role"])
    local_customer = Customer.objects.create(tenant=a["tenant"], name="Guest Alfred")
    with pytest.raises(ValidationError):
        adjust_points(**{**params, "customer_id": local_customer.pk})
    assert not LoyaltyLedgerEntry.objects.exists()
