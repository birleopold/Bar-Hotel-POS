"""Scoped customer finance snapshot; amounts are never converted or double counted."""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from apps.lodging.models import Folio, FolioLine, FolioPayment
from apps.pos.models import Order, Refund


def customer_financial_snapshot(*, tenant, customer, site_ids, outlet_ids):
    """Return a per-currency snapshot for currently visible branches/outlets.

    POS orders posted to a folio must not be counted again as standalone sales.
    Outstanding balances use signed folio charges less actual folio payments;
    refunds/reversals recorded as negative lines are preserved.
    """
    totals = defaultdict(lambda: {
        "direct_pos_sales": Decimal("0.00"),
        "direct_pos_refunds": Decimal("0.00"),
        "direct_pos_net": Decimal("0.00"),
        "folio_charges": Decimal("0.00"),
        "folio_payments": Decimal("0.00"),
        "outstanding": Decimal("0.00"),
    })
    orders = (
        Order.objects.filter(
            tenant=tenant, customer=customer,
            outlet_id__in=outlet_ids, is_paid=True, folio__isnull=True,
        ).values("currency").annotate(amount=Sum("total"))
    )
    for row in orders:
        totals[row["currency"]]["direct_pos_sales"] += row["amount"] or Decimal("0.00")

    # Apply actual refunds to standalone sales only. Folio-linked POS
    # transactions belong to the folio ledger, so including their refunds
    # here would make the customer history inconsistent.
    refunded = (
        Refund.objects.filter(
            tenant=tenant, order__tenant=tenant, order__customer=customer,
            order__outlet_id__in=outlet_ids, order__folio__isnull=True,
            order__is_paid=True,
        ).values("order__currency").annotate(amount=Sum("amount"))
    )
    for row in refunded:
        totals[row["order__currency"]]["direct_pos_refunds"] += row["amount"] or Decimal("0.00")

    folios = Folio.objects.filter(
        tenant=tenant, customer=customer, site_id__in=site_ids
    ).values_list("pk", "currency")
    by_id = dict(folios)
    charges = FolioLine.objects.filter(
        tenant=tenant, folio_id__in=by_id
    ).values("folio_id").annotate(amount=Sum("amount"))
    payments = FolioPayment.objects.filter(
        tenant=tenant, folio_id__in=by_id
    ).values("folio_id").annotate(amount=Sum("amount"))
    for row in charges:
        totals[by_id[row["folio_id"]]]["folio_charges"] += row["amount"] or Decimal("0.00")
    for row in payments:
        totals[by_id[row["folio_id"]]]["folio_payments"] += row["amount"] or Decimal("0.00")
    for amounts in totals.values():
        amounts["direct_pos_net"] = amounts["direct_pos_sales"] - amounts["direct_pos_refunds"]
        amounts["outstanding"] = amounts["folio_charges"] - amounts["folio_payments"]
    return dict(sorted(totals.items()))
