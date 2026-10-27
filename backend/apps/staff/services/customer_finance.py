"""Scoped customer finance snapshot; amounts are never converted or double counted."""

from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from django.db.models import F, Sum

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
    ).values("folio_id").annotate(
        amount=Sum(F("amount") + F("tax_amount"))
    )
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


def customer_receivable_aging(*, tenant, site_ids, currency, as_of=None, limit=25):
    """FIFO age of outstanding folio charges in one currency.

    This is charge-age analysis, not contractual overdue ageing: Folio does not
    currently store invoice due dates. Payments/negative lines reduce oldest
    charges first so no outstanding amount is counted twice.
    """
    as_of = as_of or timezone.localdate()
    folios = list(
        Folio.objects.filter(
            tenant=tenant,
            site_id__in=site_ids,
            currency=currency,
        )
        .select_related("customer", "site")
        .prefetch_related("lines", "payments")
        .order_by("created_at", "pk")
    )
    foreign_currency_folio_count = Folio.objects.filter(
        tenant=tenant,
        site_id__in=site_ids,
    ).exclude(currency=currency).count()

    totals = {
        "current_0_30": Decimal("0.00"),
        "days_31_60": Decimal("0.00"),
        "days_61_90": Decimal("0.00"),
        "days_91_plus": Decimal("0.00"),
        "outstanding": Decimal("0.00"),
    }
    rows = []
    for folio in folios:
        positives = []
        reductions = Decimal("0.00")
        for line in folio.lines.all():
            value = (line.amount or Decimal("0.00")) + (
                line.tax_amount or Decimal("0.00")
            )
            if value > 0:
                positives.append([line.created_at, value])
            elif value < 0:
                reductions += -value
        reductions += sum(
            (payment.amount or Decimal("0.00") for payment in folio.payments.all()),
            Decimal("0.00"),
        )
        positives.sort(key=lambda item: item[0])

        # FIFO application: payments/credits consume oldest charges first.
        remaining_reduction = reductions
        aged = {
            "current_0_30": Decimal("0.00"),
            "days_31_60": Decimal("0.00"),
            "days_61_90": Decimal("0.00"),
            "days_91_plus": Decimal("0.00"),
        }
        for created_at, original in positives:
            remaining = original
            if remaining_reduction > 0:
                applied = min(remaining, remaining_reduction)
                remaining -= applied
                remaining_reduction -= applied
            if remaining <= 0:
                continue
            age_days = max(
                0,
                (as_of - timezone.localtime(created_at).date()).days,
            )
            if age_days <= 30:
                bucket = "current_0_30"
            elif age_days <= 60:
                bucket = "days_31_60"
            elif age_days <= 90:
                bucket = "days_61_90"
            else:
                bucket = "days_91_plus"
            aged[bucket] += remaining

        outstanding = sum(aged.values(), Decimal("0.00"))
        if outstanding <= 0:
            continue
        for key, value in aged.items():
            totals[key] += value
        totals["outstanding"] += outstanding
        rows.append({
            "folio_id": str(folio.pk),
            "guest_name": folio.guest_name,
            "customer_name": (
                folio.customer.name
                if folio.customer_id else folio.guest_name
            ),
            "site_name": folio.site.name,
            "outstanding": outstanding,
            **aged,
        })

    rows.sort(
        key=lambda row: (-row["outstanding"], row["customer_name"].lower())
    )
    return {
        "currency": currency,
        "as_of": as_of,
        "totals": totals,
        "folios": rows[:limit],
        "folio_count": len(rows),
        "foreign_currency_folio_count": foreign_currency_folio_count,
        "method": "FIFO charge age; not contractual due-date ageing",
    }
