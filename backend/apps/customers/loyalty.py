"""Conservative loyalty foundation: immutable source-ledger and safe balance checks.

No automatic points on sale or customer discounts until rate, currency,
redemption and refund policies are explicitly configured for a tenant.
"""
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
    if current + points < 0:
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
