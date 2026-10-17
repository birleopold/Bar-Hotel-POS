"""F6 cash-neutral loyalty rewards: manager authorizations, race locks and replay."""
from decimal import Decimal
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.customers.models import Customer, LoyaltyLedgerEntry
from apps.customers.loyalty import adjust_points, points_balance, redeem_non_cash_reward
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import TenantSettings
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_non_cash_redemption_can_only_consume_existing_points_once():
    a = _seed_tenant_bundle(name="F6 Reward", slug="f6-reward", user_email="f6-reward@test.local")
    customer = Customer.objects.create(tenant=a["tenant"], name="Customer Reward")
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    policy, _ = TenantSettings.objects.get_or_create(tenant=a["tenant"])
    policy.loyalty_enabled = True
    policy.save(update_fields=["loyalty_enabled"])
    adjust_points(tenant=a["tenant"], customer_id=customer.pk, user=a["user"],
                  membership=member, points=10, reason="Welcome customer non-cash reward points",
                  source_key=str(uuid4()))
    params = dict(tenant=a["tenant"], customer_id=customer.pk, membership=member,
                  user=a["user"], points=6, benefit="Reusable shopping tote issued to customer",
                  source_key=str(uuid4()))
    first, duplicate = redeem_non_cash_reward(**params)
    assert not duplicate and first.points == -6
    again, duplicate = redeem_non_cash_reward(**params)
    assert duplicate and again.pk == first.pk
    assert points_balance(tenant=a["tenant"], customer=customer) == 4
    with pytest.raises(ValidationError):
        redeem_non_cash_reward(**{**params, "points": 7})
    with pytest.raises(ValidationError):
        redeem_non_cash_reward(**{**params, "points": 5, "source_key": str(uuid4())})
    assert LoyaltyLedgerEntry.objects.filter(customer=customer, source_type="redemption").count() == 1


@pytest.mark.django_db
def test_redemption_rejects_staff_foreign_customers_and_disabled_loyalty():
    a = _seed_tenant_bundle(name="F6 Reward A", slug="f6-rew-a", user_email="f6-ra@test.local")
    b = _seed_tenant_bundle(name="F6 Reward B", slug="f6-rew-b", user_email="f6-rb@test.local")
    customer = Customer.objects.create(tenant=a["tenant"], name="Reward person")
    foreign = Customer.objects.create(tenant=b["tenant"], name="Foreign person")
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    params = dict(tenant=a["tenant"], customer_id=customer.pk, membership=member,
                  user=a["user"], points=2, benefit="Reusable checkout bag supplied",
                  source_key=str(uuid4()))
    with pytest.raises(ValidationError):
        redeem_non_cash_reward(**params)
    settings, _ = TenantSettings.objects.get_or_create(tenant=a["tenant"])
    settings.loyalty_enabled = True
    settings.save(update_fields=["loyalty_enabled"])
    with pytest.raises(ValidationError):
        redeem_non_cash_reward(**{**params, "customer_id": foreign.pk})
    member.role = MembershipRole.STOREKEEPER
    member.save(update_fields=["role"])
    with pytest.raises(ValidationError):
        redeem_non_cash_reward(**params)
    assert LoyaltyLedgerEntry.objects.filter(tenant=a["tenant"]).count() == 0


@pytest.mark.django_db
def test_manager_redemption_visible_in_existing_customer_profile():
    a = _seed_tenant_bundle(name="F6 Reward UI", slug="f6-rew-ui", user_email="f6-rew-ui@test.local")
    customer = Customer.objects.create(tenant=a["tenant"], name="Manager Reward UI", created_by=a["user"])
    settings, _ = TenantSettings.objects.get_or_create(tenant=a["tenant"])
    settings.loyalty_enabled = True
    settings.save(update_fields=["loyalty_enabled"])
    client = Client()
    assert client.login(username=a["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(a["tenant"].pk)
    session.save()
    response = client.get(reverse("staff-customer-detail", kwargs={"customer_id": customer.pk}))
    assert response.status_code == 200, response.content
    assert b"Redeem a non-cash reward" in response.content
