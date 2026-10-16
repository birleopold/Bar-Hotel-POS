"""Actual POS settlement and return lifecycle with optional customer rewards."""
import uuid
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership
from apps.customers.models import Customer, LoyaltyLedgerEntry
from apps.customers.loyalty import adjust_points, points_balance
from apps.customers.services import merge_customers
from apps.pos.models import Order, Payment
from apps.pos.services.payments import record_order_payment, record_order_refund
from apps.tenants.models import TenantSettings
from tests.test_phase1_isolation_and_idempotency import (
    _create_open_order, _seed_tenant_bundle,
)


def new_sale(a, *, currency="USD", linked=True):
    customer = Customer.objects.create(tenant=a["tenant"], name="Customer of loyalty sale")
    order = _create_open_order(tenant=a["tenant"], outlet=a["outlet"], total="100.00")
    order.currency = currency
    order.subtotal = Decimal("90.00")
    order.tax_total = Decimal("20.00")
    order.discount_amount = Decimal("10.00")
    order.customer = customer if linked else None
    order.save(update_fields=[
        "currency", "subtotal", "tax_total", "discount_amount", "customer",
    ])
    settings = TenantSettings.objects.get(tenant=a["tenant"])
    settings.loyalty_enabled = True
    settings.loyalty_spend_per_point = Decimal("10.00")
    settings.default_currency = "USD"
    settings.save(update_fields=[
        "loyalty_enabled", "loyalty_spend_per_point", "default_currency",
    ])
    return order, customer, settings


@pytest.mark.django_db
def test_partial_payment_earns_nothing_until_fully_paid_then_once():
    a = _seed_tenant_bundle(
        name="Reward Sale", slug="reward-sale", user_email="reward-sale@pos.test",
    )
    order, customer, settings = new_sale(a)
    p1, replay = record_order_payment(
        order=order, user=a["user"], method="cash",
        amount=Decimal("40.00"), idempotency_key="reward-pay-01",
    )
    assert not replay
    assert not LoyaltyLedgerEntry.objects.filter(source_type="sale").exists()
    p2, replay = record_order_payment(
        order=order, user=a["user"], method="cash",
        amount=Decimal("60.00"), idempotency_key="reward-pay-02",
    )
    assert not replay
    p2_again, repeated = record_order_payment(
        order=order, user=a["user"], method="cash",
        amount=Decimal("60.00"), idempotency_key="reward-pay-02",
    )
    assert repeated and p2_again.pk == p2.pk
    entry = LoyaltyLedgerEntry.objects.get(
        tenant=a["tenant"], source_type="sale", source_key=str(order.pk),
    )
    # 90 before tax - 10 discount = 80 eligible -> 8 points, not 10.
    assert entry.points == 8
    assert points_balance(tenant=a["tenant"], customer=customer) == 8
    assert LoyaltyLedgerEntry.objects.filter(source_type="sale").count() == 1


@pytest.mark.django_db
def test_refunds_reverse_only_original_points_at_cumulative_partial_rate():
    a = _seed_tenant_bundle(
        name="Reward Refund", slug="reward-refund", user_email="reward-refund@pos.test",
    )
    order, customer, settings = new_sale(a)
    record_order_payment(
        order=order, user=a["user"], method="cash",
        amount=Decimal("100.00"), idempotency_key="reward-refund-pay",
    )
    settings.loyalty_enabled = False
    settings.loyalty_spend_per_point = Decimal("99999.00")
    settings.save(update_fields=["loyalty_enabled", "loyalty_spend_per_point"])
    first, replay = record_order_refund(
        order=order, user=a["user"], amount=Decimal("25.00"),
        reason="Partial return", idempotency_key="reward-r-01",
        restock=False,
    )
    assert not replay
    assert LoyaltyLedgerEntry.objects.get(
        source_type="refund", source_key=str(first.pk),
    ).points == -2
    assert points_balance(tenant=a["tenant"], customer=customer) == 6
    second, replay = record_order_refund(
        order=order, user=a["user"], amount=Decimal("75.00"),
        reason="Final return", idempotency_key="reward-r-02",
        restock=False,
    )
    assert not replay
    assert LoyaltyLedgerEntry.objects.get(
        source_type="refund", source_key=str(second.pk),
    ).points == -6
    assert points_balance(tenant=a["tenant"], customer=customer) == 0
    again, replay = record_order_refund(
        order=order, user=a["user"], amount=Decimal("75.00"),
        reason="Final return", idempotency_key="reward-r-02",
        restock=False,
    )
    assert replay and again.pk == second.pk
    assert LoyaltyLedgerEntry.objects.filter(source_type="refund").count() == 2


@pytest.mark.django_db
def test_refund_never_blocks_customer_money_if_points_already_used():
    a = _seed_tenant_bundle(
        name="Reward Debt", slug="reward-debt", user_email="reward-debt@pos.test",
    )
    order, customer, _settings = new_sale(a)
    record_order_payment(
        order=order, user=a["user"], method="cash",
        amount=Decimal("100.00"), idempotency_key="reward-debt-pay",
    )
    membership = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    adjust_points(
        tenant=a["tenant"], customer_id=customer.pk, membership=membership,
        user=a["user"], points=-8, reason="Authorized correction of earned points",
        source_key=str(uuid.uuid4()),
    )
    result, replay = record_order_refund(
        order=order, user=a["user"], amount=Decimal("100.00"),
        reason="Complete refund", idempotency_key="reward-debt-r",
        restock=False,
    )
    assert not replay
    assert result.amount == Decimal("100.00")
    assert points_balance(tenant=a["tenant"], customer=customer) == -8


@pytest.mark.django_db
def test_customer_merge_transfers_points_and_preserves_refund_source():
    a = _seed_tenant_bundle(
        name="Reward Merge", slug="reward-merge", user_email="reward-merge@pos.test",
    )
    order, old, settings = new_sale(a)
    keep = Customer.objects.create(tenant=a["tenant"], name="Verified person")
    record_order_payment(
        order=order, user=a["user"], method="cash",
        amount=Decimal("100.00"), idempotency_key="reward-merge-pay",
    )
    merged, counts = merge_customers(
        source=old, target=keep, tenant_id=a["tenant"].pk,
        user=a["user"], reason="Government ID and phone confirmed by owner",
    )
    assert merged.pk == keep.pk
    assert counts["loyalty_entries"] == 1
    order.refresh_from_db()
    assert order.customer_id == keep.pk
    assert points_balance(tenant=a["tenant"], customer=keep) == 8
    record_order_refund(
        order=order, user=a["user"], amount=Decimal("50.00"),
        reason="Returned goods", idempotency_key="reward-merge-r",
        restock=False,
    )
    assert points_balance(tenant=a["tenant"], customer=keep) == 4
    assert not LoyaltyLedgerEntry.objects.filter(customer=old).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("disabled, currency, linked", [
    (True, "USD", True),
    (False, "EUR", True),
    (False, "USD", False),
])
def test_earning_is_opt_in_currency_scoped_and_needs_customer(disabled, currency, linked):
    key = "reward-policy-" + str(uuid.uuid4())[:8]
    a = _seed_tenant_bundle(
        name="Reward Policy", slug=key, user_email=key + "@pos.test",
    )
    order, customer, settings = new_sale(a, currency=currency, linked=linked)
    settings.loyalty_enabled = not disabled
    settings.save(update_fields=["loyalty_enabled"])
    record_order_payment(
        order=order, user=a["user"], method="cash",
        amount=Decimal("100.00"), idempotency_key=key + "-paid",
    )
    assert not LoyaltyLedgerEntry.objects.filter(source_type="sale").exists()
