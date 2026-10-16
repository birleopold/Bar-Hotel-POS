"""Optional tenant loyalty program with audited sale awards and refund reversals.

Redemption is not enabled until rewards have a defined monetary/benefit policy.
Refunds must remain possible even if points were already spent elsewhere.
"""
from decimal import Decimal, ROUND_FLOOR
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError
from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from .models import Customer, LoyaltyLedgerEntry

MANAGER_ROLES = {
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
}


def points_balance(*, tenant, customer):
    if customer.tenant_id != tenant.pk or customer.merged_into_id:
        raise ValidationError({"customer": "Choose an active customer in your business."})
    return LoyaltyLedgerEntry.objects.filter(
        tenant=tenant, customer=customer,
    ).aggregate(points=Sum("points"))["points"] or 0


@transaction.atomic
def adjust_points(*, tenant, customer_id, membership, user, points, reason, source_key):
    if (not membership or not membership.is_active
            or membership.tenant_id != tenant.pk or membership.user_id != user.pk
            or membership.role not in MANAGER_ROLES):
        raise ValidationError({"detail": "Only an authorized manager can adjust points."})
    if isinstance(points, bool) or not isinstance(points, int) or not -100000 <= points <= 100000 or points == 0:
        raise ValidationError({"points": "Enter whole points from -100,000 to 100,000, excluding zero."})
    reason = (reason or "").strip()
    if len(reason) < 12 or len(reason) > 300:
        raise ValidationError({"reason": "Explain the adjustment in 12 to 300 characters."})
    source_key = (source_key or "").strip()
    if not source_key or len(source_key) > 128:
        raise ValidationError({"source_key": "A unique request key is required."})
    customer = Customer.objects.select_for_update().filter(
        tenant=tenant, pk=customer_id, merged_into__isnull=True,
    ).first()
    if not customer:
        raise ValidationError({"customer": "Customer not found in this business."})
    existing = LoyaltyLedgerEntry.objects.filter(
        tenant=tenant, source_type="adjustment", source_key=source_key,
    ).first()
    if existing:
        if (existing.customer_id != customer.pk or existing.points != points
                or existing.reason != reason):
            raise ValidationError({"source_key": "This request key was used for a different adjustment."})
        return existing, True
    current = points_balance(tenant=tenant, customer=customer)
    # Refund reversals may legitimately leave points to recover. Positive
    # corrections must remain possible even while the balance is negative;
    # only a *new manual deduction* is forbidden from overdrawing points.
    if points < 0 and current + points < 0:
        raise ValidationError({"points": "This would reduce the customer balance below zero."})
    entry = LoyaltyLedgerEntry.objects.create(
        tenant=tenant, customer=customer, points=points,
        source_type="adjustment", source_key=source_key,
        reason=reason, recorded_by=user,
    )
    log_audit(
        tenant_id=tenant.pk, user_id=user.pk,
        action="customer.loyalty_adjusted", entity_type="loyalty_entry",
        entity_id=str(entry.pk),
        payload={"points": points, "customer_id": str(customer.pk), "reason": reason},
    )
    return entry, False


_MAX_POINTS_PER_SALE = 1_000_000


def eligible_spend_for_order(order):
    """Discount-adjusted subtotal excluding tax, never above the sale total."""
    subtotal = max(Decimal("0.00"), order.subtotal - order.discount_amount)
    return min(subtotal, max(Decimal("0.00"), order.total))


def award_paid_order_points(*, order, user):
    """Award once for a fully paid linked sale, in the payment transaction."""
    from apps.tenants.models import TenantSettings

    if not order.is_paid or not order.customer_id:
        return None
    policy = TenantSettings.objects.filter(tenant_id=order.tenant_id).only(
        "loyalty_enabled", "loyalty_spend_per_point", "default_currency",
    ).first()
    if (policy is None or not policy.loyalty_enabled
            or order.currency != policy.default_currency
            or not policy.loyalty_spend_per_point or policy.loyalty_spend_per_point <= 0):
        return None

    existing = LoyaltyLedgerEntry.objects.filter(
        tenant_id=order.tenant_id, source_type="sale", source_key=str(order.pk),
    ).first()
    if existing:
        return existing

    customer = Customer.objects.select_for_update().filter(
        tenant_id=order.tenant_id, pk=order.customer_id, merged_into__isnull=True,
    ).first()
    if customer is None:
        return None
    spend = eligible_spend_for_order(order)
    if spend <= 0:
        return None
    raw_points = int((spend / policy.loyalty_spend_per_point).to_integral_value(
        rounding=ROUND_FLOOR,
    ))
    points = min(_MAX_POINTS_PER_SALE, raw_points)
    if points <= 0:
        return None

    entry = LoyaltyLedgerEntry.objects.create(
        tenant_id=order.tenant_id, customer=customer, points=points,
        source_type="sale", source_key=str(order.pk),
        reason=(
            f"Paid order {order.bill_reference}: {order.currency} {spend:.2f} "
            f"eligible at {policy.loyalty_spend_per_point:.2f} per point"
        )[:300],
        recorded_by=user,
    )
    log_audit(
        tenant_id=order.tenant_id, user_id=user.pk if user else None,
        action="customer.loyalty_earned", entity_type="loyalty_entry",
        entity_id=str(entry.pk), payload={
            "outlet_id": str(order.outlet_id),
            "order_id": str(order.pk), "points": points,
        },
    )
    return entry


def reverse_refunded_order_points(*, order, refund, user):
    """Reverse original points proportionally, regardless of today's earn rate.

    Called under the POS order lock and refund transaction. A return never
    fails because previously earned points were already redeemed.
    """
    from apps.pos.models import Refund

    award = LoyaltyLedgerEntry.objects.filter(
        tenant_id=order.tenant_id, source_type="sale", source_key=str(order.pk),
    ).first()
    if not award:
        return None
    already = LoyaltyLedgerEntry.objects.filter(
        tenant_id=order.tenant_id, source_type="refund", source_key=str(refund.pk),
    ).first()
    if already:
        return already
    customer = Customer.objects.select_for_update().filter(
        tenant_id=order.tenant_id, pk=award.customer_id,
    ).first()
    if customer is None:
        raise ValidationError({"loyalty": "Original customer loyalty account missing."})
    previous_ids = [str(pk) for pk in Refund.objects.filter(
        tenant_id=order.tenant_id, order=order,
    ).exclude(pk=refund.pk).values_list("pk", flat=True)]
    prior = -(LoyaltyLedgerEntry.objects.filter(
        tenant_id=order.tenant_id, customer=customer, source_type="refund",
        source_key__in=previous_ids,
    ).aggregate(total=Sum("points"))["total"] or 0)
    refunded_amount = Refund.objects.filter(
        tenant_id=order.tenant_id, order=order,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    if order.total <= 0:
        return None
    fraction = min(Decimal("1"), refunded_amount / order.total)
    target = int((Decimal(award.points) * fraction).to_integral_value(
        rounding=ROUND_FLOOR,
    ))
    delta = max(0, target - prior)
    if not delta:
        return None

    entry = LoyaltyLedgerEntry.objects.create(
        tenant_id=order.tenant_id, customer=customer, points=-delta,
        source_type="refund", source_key=str(refund.pk),
        reason=f"Refund on order {order.bill_reference}"[:300],
        recorded_by=user,
    )
    log_audit(
        tenant_id=order.tenant_id, user_id=user.pk if user else None,
        action="customer.loyalty_refund_reversed",
        entity_type="loyalty_entry", entity_id=str(entry.pk),
        payload={
            "outlet_id": str(order.outlet_id), "order_id": str(order.pk),
            "refund_id": str(refund.pk), "points": -delta,
        },
    )
    return entry
