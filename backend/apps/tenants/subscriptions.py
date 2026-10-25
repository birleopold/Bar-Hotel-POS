from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from .models import SubscriptionStatus, Tenant, TenantSubscription


@dataclass(frozen=True)
class TenantOperationalAccess:
    allowed: bool
    reason: str
    message: str


def tenant_operational_access(tenant: Tenant, *, now=None) -> TenantOperationalAccess:
    """Return whether ordinary tenant operations may continue.

    Platform pause remains the strongest gate. Existing workspaces without a
    subscription are left operational for backwards-compatible migration.
    Past-due subscriptions stay operational until the platform explicitly
    suspends them; suspended/cancelled subscriptions and expired trials do not.
    """
    if not getattr(tenant, "is_active", True):
        return TenantOperationalAccess(
            False,
            "workspace_paused",
            "This workspace is currently paused by the platform.",
        )

    try:
        subscription = tenant.subscription
    except TenantSubscription.DoesNotExist:
        return TenantOperationalAccess(True, "unmanaged", "")

    if subscription.status == SubscriptionStatus.SUSPENDED:
        return TenantOperationalAccess(
            False,
            "subscription_suspended",
            "This workspace subscription is suspended. Contact your platform administrator.",
        )
    if subscription.status == SubscriptionStatus.CANCELLED:
        return TenantOperationalAccess(
            False,
            "subscription_cancelled",
            "This workspace subscription is cancelled. Contact your platform administrator to reactivate it.",
        )
    if subscription.status == SubscriptionStatus.TRIAL and subscription.trial_ends_at:
        current = now or timezone.now()
        if subscription.trial_ends_at <= current:
            return TenantOperationalAccess(
                False,
                "trial_expired",
                "This workspace trial has ended. Contact your platform administrator to continue.",
            )

    # ACTIVE and PAST_DUE continue operating. Past-due access is deliberately
    # separated from suspension so the platform can apply a grace period.
    return TenantOperationalAccess(True, subscription.status, "")
