"""Database-backed reconciliation regression tests for Phase 06."""
import pytest

from apps.customers.models import Customer, LoyaltyLedgerEntry
from apps.customers.loyalty_reconciliation import (
    reconcile_loyalty_account,
    reconcile_loyalty_tenant,
)
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_read_only_reconciliation_handles_negative_and_positive_customer_balances():
    a = _seed_tenant_bundle(
        name="Ledger Review East", slug="ledger-review-east",
        user_email="ledger-review-east@test.local",
    )
    tenant = a["tenant"]
    one = Customer.objects.create(tenant=tenant, name="First account")
    two = Customer.objects.create(tenant=tenant, name="Second account")
    for customer, kind, points, key in [
        (one, "sale", 5, "review-sale-one"),
        (one, "refund", -7, "review-refund-one"),
        (two, "sale", 11, "review-sale-two"),
        (two, "adjustment", -3, "review-adjust-two"),
    ]:
        LoyaltyLedgerEntry.objects.create(
            tenant=tenant, customer=customer, source_type=kind,
            points=points, source_key=key, reason="Review snapshot test",
        )

    negative = reconcile_loyalty_account(tenant=tenant, customer=one)
    assert negative["balance"] == -2
    assert negative["points_to_recover"] == 2
    assert negative["sale_reversals_exceed_earnings"] is True

    summary = reconcile_loyalty_tenant(tenant=tenant)
    assert summary["earned"] == 16
    assert summary["refund_reversals"] == -7
    assert summary["manager_adjustments"] == -3
    assert summary["net_points_outstanding"] == 6
    assert summary["accounts_with_negative_points"] == 1
    assert LoyaltyLedgerEntry.objects.filter(tenant=tenant).count() == 4


@pytest.mark.django_db
def test_reconciliation_never_includes_another_business_or_merged_accounts():
    a = _seed_tenant_bundle(
        name="Reconcile South", slug="reconcile-south",
        user_email="reconcile-south@test.local",
    )
    b = _seed_tenant_bundle(
        name="Reconcile North", slug="reconcile-north",
        user_email="reconcile-north@test.local",
    )
    active = Customer.objects.create(tenant=a["tenant"], name="Active")
    merged = Customer.objects.create(tenant=a["tenant"], name="Merged", merged_into=active)
    foreign = Customer.objects.create(tenant=b["tenant"], name="Other")
    for tenant, customer, key, points in [
        (a["tenant"], active, "active-points", 3),
        (a["tenant"], merged, "legacy-merged-points", -20),
        (b["tenant"], foreign, "foreign-points", -100),
    ]:
        LoyaltyLedgerEntry.objects.create(
            tenant=tenant, customer=customer, source_type="adjustment",
            source_key=key, points=points, reason="Isolation test",
        )
    summary = reconcile_loyalty_tenant(tenant=a["tenant"])
    assert summary["net_points_outstanding"] == 3
    assert summary["accounts_with_negative_points"] == 0
    with pytest.raises(ValueError):
        reconcile_loyalty_account(tenant=a["tenant"], customer=foreign)
    with pytest.raises(ValueError):
        reconcile_loyalty_account(tenant=a["tenant"], customer=merged)
