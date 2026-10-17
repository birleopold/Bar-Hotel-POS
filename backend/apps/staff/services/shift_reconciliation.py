"""Shift register evidence: recorded shift-linked money, never guessed cash settlement."""
from collections import defaultdict
from decimal import Decimal


def build_shift_reconciliation(shift):
    from apps.pos.models import Payment, Refund, ShiftHandover

    payments = list(Payment.objects.filter(
        tenant_id=shift.tenant_id, shift_id=shift.pk, order__outlet_id=shift.outlet_id,
    ).select_related("order", "recorded_by").order_by("-created_at"))
    refunds = list(Refund.objects.filter(
        tenant_id=shift.tenant_id, shift_id=shift.pk, order__outlet_id=shift.outlet_id,
    ).select_related("order", "payment", "recorded_by").order_by("-created_at"))
    totals = defaultdict(lambda: {"gross": Decimal("0"), "refunds": Decimal("0")})
    for payment in payments:
        totals[(payment.order.currency, payment.method)]["gross"] += payment.amount
    for refund in refunds:
        # A refund's payment method is not separately captured by the database.
        # Show it as attributable to its original sale's tender, not as proof
        # of which method actually paid the refund.
        totals[(refund.order.currency, refund.payment.method)]["refunds"] += refund.amount
    methods = []
    for (currency, method), values in sorted(totals.items()):
        methods.append({
            "currency": currency, "method": method,
            "gross": values["gross"], "refunded": values["refunds"],
            "net": values["gross"] - values["refunds"],
        })
    return {
        "methods": methods,
        "payments_count": len(payments),
        "refunds_count": len(refunds),
        "recent_payments": payments[:20],
        "recent_refunds": refunds[:20],
        "is_exact_attribution": bool(shift.cash_attribution),
        "handover": ShiftHandover.objects.filter(
            shift=shift, tenant_id=shift.tenant_id,
        ).select_related("verified_by", "approved_by", "accepted_by").first(),
    }
