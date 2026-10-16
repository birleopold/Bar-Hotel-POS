"""An entitlement can extend a plan but not override the customer's disabled modules."""
import pytest

from apps.staff.services.modules import resolve_effective_staff_modules
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
