"""Read-only integrity checks for optional customer reward points.

This module never corrects historical points or edits financial transactions.
Operational dashboards can call reconcile_loyalty_account before an explicitly
approved correction. Negative balances can be legitimate after a refund.
"""
from django.db.models import Sum

from .models import Customer, LoyaltyLedgerEntry


def reconcile_loyalty_account(*, tenant, customer):
    """Explain a customer's point balance using its immutable ledger.

    A negative net balance is not automatically a defect: legitimate refunds
    can reverse rewards that were already spent. A manual correction is never
    inferred or applied by this function.
    """
    if customer.tenant_id != tenant.pk or customer.merged_into_id:
        raise ValueError("Select an active customer in the specified business.")
    rows = (
        LoyaltyLedgerEntry.objects.filter(tenant=tenant, customer=customer)
        .values("source_type")
        .annotate(net=Sum("points"))
    )
    amounts = {row["source_type"]: row["net"] for row in rows}
    earned = amounts.get("sale", 0)
    refunded = amounts.get("refund", 0)
    adjustments = amounts.get("adjustment", 0)
    redeemed = amounts.get("redemption", 0)
    net = earned + refunded + adjustments + redeemed
    return {
        "customer_id": str(customer.pk),
        "earned": earned,
        "refund_reversals": refunded,
        "redemptions": redeemed,
        "manager_adjustments": adjustments,
        "balance": net,
        "points_to_recover": max(0, -net),
        "sale_reversals_exceed_earnings": -refunded > earned,
    }


def reconcile_loyalty_tenant(*, tenant):
    """Read-only, tenant-scoped summary; no names, contacts or ledger mutation."""
    # The ledger is authoritative. Grouped SQL avoids loading one customer
    # or one ledger entry at a time into application memory.
    active_customers = Customer.objects.filter(
        tenant=tenant, merged_into__isnull=True,
    ).values_list("pk", flat=True)
    entries = LoyaltyLedgerEntry.objects.filter(
        tenant=tenant, customer_id__in=active_customers,
    )
    totals = {
        row["source_type"]: row["net"]
        for row in entries.values("source_type").annotate(net=Sum("points"))
    }
    balances = entries.values("customer_id").annotate(net=Sum("points"))
    accounts_with_negative_points = balances.filter(net__lt=0).count()
    net = sum(totals.values())
    return {
        "earned": totals.get("sale", 0),
        "refund_reversals": totals.get("refund", 0),
        "redemptions": totals.get("redemption", 0),
        "manager_adjustments": totals.get("adjustment", 0),
        "net_points_outstanding": net,
        "accounts_with_negative_points": accounts_with_negative_points,
    }
