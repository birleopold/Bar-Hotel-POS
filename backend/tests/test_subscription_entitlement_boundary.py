"""Subscription and entitlement boundaries for tenant operations."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.staff.services.modules import resolve_effective_staff_modules
from apps.tenants.subscriptions import tenant_operational_access
from apps.tenants.models import (
    Plan, SubscriptionStatus, Tenant, TenantFeatureEntitlement,
    TenantSettings, TenantSubscription,
)


@pytest.mark.django_db
def test_entitlement_does_not_reenable_owner_disabled_area():
    tenant = Tenant.objects.create(name="Restricted modules", slug="restricted-entitlement")
    TenantSettings.objects.create(
        tenant=tenant,
        business_lines=["bar"],
        enabled_staff_modules=["pos", "inventory", "workspace"],
    )
    plan = Plan.objects.create(
        name="Restricted Base Plan", code="restricted-base",
        included_modules=["pos", "workspace"],
    )
    TenantSubscription.objects.create(
        tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE,
    )
    TenantFeatureEntitlement.objects.create(
        tenant=tenant, module_key="purchasing", is_enabled=True,
    )
    TenantFeatureEntitlement.objects.create(
        tenant=tenant, module_key="inventory", is_enabled=True,
    )
    modules = resolve_effective_staff_modules(tenant)
    assert "inventory" in modules  # Explicit plan extension, enabled by owner.
    assert "purchasing" not in modules  # Owner disabled this area.


def test_delivery_is_exposed_in_control_plane_choices_but_not_default_enabled():
    from apps.tenants.models import (
        STAFF_MODULE_KEYS,
        default_enabled_staff_modules,
        staff_module_choices,
    )
    choices = dict(staff_module_choices())
    assert choices["delivery"] == "Delivery / fulfillment"
    assert "delivery" in STAFF_MODULE_KEYS
    assert "delivery" not in default_enabled_staff_modules()


@pytest.mark.django_db
def test_delivery_is_optional_and_requires_owner_plus_plan_enablement():
    tenant = Tenant.objects.create(name="Optional delivery", slug="optional-delivery")
    settings = TenantSettings.objects.create(
        tenant=tenant,
        business_lines=["retail"],
        enabled_staff_modules=["pos", "workspace"],
    )
    plan = Plan.objects.create(
        name="Delivery Plan", code="delivery-plan",
        included_modules=["pos", "workspace", "delivery"],
    )
    TenantSubscription.objects.create(
        tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE,
    )
    assert "delivery" not in resolve_effective_staff_modules(tenant)

    settings.enabled_staff_modules = ["pos", "workspace", "delivery"]
    settings.save(update_fields=["enabled_staff_modules", "updated_at"])
    assert "delivery" in resolve_effective_staff_modules(tenant)


@pytest.mark.django_db
def test_delivery_entitlement_cannot_leak_into_lodging_only_profile():
    tenant = Tenant.objects.create(name="Hotel only", slug="hotel-delivery-boundary")
    TenantSettings.objects.create(
        tenant=tenant,
        business_lines=["lodging"],
        enabled_staff_modules=["lodging", "workspace", "delivery"],
    )
    plan = Plan.objects.create(
        name="Hotel Plan", code="hotel-plan-delivery-boundary",
        included_modules=["lodging", "workspace", "delivery"],
    )
    TenantSubscription.objects.create(
        tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE,
    )
    assert "delivery" not in resolve_effective_staff_modules(tenant)


@pytest.mark.django_db
def test_entitlement_cannot_widen_business_profile():
    tenant = Tenant.objects.create(name="Retail Module Policy", slug="retail-module-entitlement")
    TenantSettings.objects.create(
        tenant=tenant, business_lines=["retail"], enabled_staff_modules=["pos", "workspace"],
    )
    plan = Plan.objects.create(
        name="Retail Restricted", code="retail-restricted", included_modules=["workspace"],
    )
    TenantSubscription.objects.create(
        tenant=tenant, plan=plan, status=SubscriptionStatus.ACTIVE,
    )
    TenantFeatureEntitlement.objects.create(
        tenant=tenant, module_key="lodging", is_enabled=True,
    )
    assert "lodging" not in resolve_effective_staff_modules(tenant)


@pytest.mark.django_db
def test_subscription_operational_access_policy_is_fail_closed_for_explicit_blocks():
    active = Tenant.objects.create(name="Active subscription", slug="sub-active-boundary")
    TenantSettings.objects.create(tenant=active)
    plan = Plan.objects.create(name="Boundary Plan", code="boundary-plan")
    subscription = TenantSubscription.objects.create(
        tenant=active, plan=plan, status=SubscriptionStatus.ACTIVE,
    )
    assert tenant_operational_access(active).allowed

    subscription.status = SubscriptionStatus.PAST_DUE
    subscription.save(update_fields=["status", "updated_at"])
    assert tenant_operational_access(active).allowed

    subscription.status = SubscriptionStatus.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    state = tenant_operational_access(active)
    assert not state.allowed
    assert state.reason == "subscription_suspended"

    subscription.status = SubscriptionStatus.CANCELLED
    subscription.save(update_fields=["status", "updated_at"])
    state = tenant_operational_access(active)
    assert not state.allowed
    assert state.reason == "subscription_cancelled"

    subscription.status = SubscriptionStatus.TRIAL
    subscription.trial_ends_at = timezone.now() - timedelta(minutes=1)
    subscription.save(update_fields=["status", "trial_ends_at", "updated_at"])
    state = tenant_operational_access(active)
    assert not state.allowed
    assert state.reason == "trial_expired"

    legacy = Tenant.objects.create(name="Legacy no subscription", slug="legacy-no-subscription")
    TenantSettings.objects.create(tenant=legacy)
    assert tenant_operational_access(legacy).allowed


@pytest.mark.django_db
def test_suspended_subscription_redirects_staff_to_workspace_status(client):
    tenant = Tenant.objects.create(name="Suspended shop", slug="suspended-shop")
    TenantSettings.objects.create(tenant=tenant, business_lines=["retail"])
    plan = Plan.objects.create(name="Suspended Plan", code="suspended-plan")
    TenantSubscription.objects.create(
        tenant=tenant, plan=plan, status=SubscriptionStatus.SUSPENDED,
    )
    user = get_user_model().objects.create_user(
        email="suspended-worker@example.test", password="StrongPass!2026",
    )
    Membership.objects.create(
        user=user, tenant=tenant, role=MembershipRole.OWNER,
    )
    client.force_login(user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(tenant.pk)
    session.save()

    response = client.get(reverse("staff-dashboard"))
    assert response.status_code == 302
    assert response["Location"] == reverse("staff-pending-approval")
    status_page = client.get(response["Location"])
    assert status_page.status_code == 200
    assert b"subscription is suspended" in status_page.content.lower()
