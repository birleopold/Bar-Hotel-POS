"""Cross-phase P15 release boundaries that must remain true together."""
from decimal import Decimal

import pytest

from apps.accounts.models import Membership, MembershipRole, User
from apps.pos.models import Order
from apps.staff.services import get_tenant_staff_modules, staff_nav_visibility_scoped
from apps.tenants.models import (
    Outlet,
    OutletType,
    Plan,
    Site,
    SubscriptionStatus,
    Tenant,
    TenantSettings,
    TenantSubscription,
)


@pytest.mark.django_db
def test_two_tenants_keep_currency_and_optional_delivery_isolated():
    ug = Tenant.objects.create(name="Uganda Retail", slug="release-ug-retail")
    ke = Tenant.objects.create(name="Kenya Retail", slug="release-ke-retail")
    ug_settings = TenantSettings.objects.create(
        tenant=ug,
        business_lines=["retail"],
        default_currency="UGX",
        enabled_staff_modules=["pos", "workspace", "delivery"],
    )
    TenantSettings.objects.create(
        tenant=ke,
        business_lines=["retail"],
        default_currency="KES",
        enabled_staff_modules=["pos", "workspace"],
    )

    ug_plan = Plan.objects.create(
        name="UG Retail Delivery",
        code="release-ug-delivery",
        included_modules=["pos", "workspace", "delivery"],
    )
    ke_plan = Plan.objects.create(
        name="KE Retail",
        code="release-ke-retail",
        included_modules=["pos", "workspace", "delivery"],
    )
    TenantSubscription.objects.create(
        tenant=ug, plan=ug_plan, status=SubscriptionStatus.ACTIVE,
    )
    TenantSubscription.objects.create(
        tenant=ke, plan=ke_plan, status=SubscriptionStatus.ACTIVE,
    )

    ug_site = Site.objects.create(tenant=ug, name="Kampala")
    ke_site = Site.objects.create(tenant=ke, name="Nairobi")
    ug_outlet = Outlet.objects.create(
        site=ug_site, name="Main shop", outlet_type=OutletType.RETAIL,
    )
    ke_outlet = Outlet.objects.create(
        site=ke_site, name="Main shop", outlet_type=OutletType.RETAIL,
    )

    ug_user = User.objects.create_user(
        email="release-ug@example.test", password="SafePass!2026",
    )
    ke_user = User.objects.create_user(
        email="release-ke@example.test", password="SafePass!2026",
    )
    ug_member = Membership.objects.create(
        user=ug_user, tenant=ug, role=MembershipRole.OWNER,
    )
    ke_member = Membership.objects.create(
        user=ke_user, tenant=ke, role=MembershipRole.OWNER,
    )

    ug_modules = get_tenant_staff_modules(ug, outlet=ug_outlet)
    ke_modules = get_tenant_staff_modules(ke, outlet=ke_outlet)
    assert "delivery" in ug_modules
    assert "delivery" not in ke_modules

    ug_nav = staff_nav_visibility_scoped(
        ug_member, modules=ug_modules, tenant=ug, outlet=ug_outlet,
    )
    ke_nav = staff_nav_visibility_scoped(
        ke_member, modules=ke_modules, tenant=ke, outlet=ke_outlet,
    )
    assert ug_nav.delivery
    assert not ke_nav.delivery

    ug_order = Order.objects.create(
        tenant=ug, outlet=ug_outlet, currency="USD", total=Decimal("1000"),
    )
    ke_order = Order.objects.create(
        tenant=ke, outlet=ke_outlet, currency="USD", total=Decimal("1000"),
    )
    assert ug_order.currency == ug_settings.default_currency == "UGX"
    assert ke_order.currency == "KES"


@pytest.mark.django_db
def test_delivery_capability_cannot_escape_retail_business_boundary():
    hotel = Tenant.objects.create(name="Release Hotel", slug="release-hotel")
    TenantSettings.objects.create(
        tenant=hotel,
        business_lines=["lodging"],
        default_currency="UGX",
        enabled_staff_modules=["lodging", "workspace", "delivery"],
    )
    plan = Plan.objects.create(
        name="Release Hotel Plan",
        code="release-hotel-plan",
        included_modules=["lodging", "workspace", "delivery"],
    )
    TenantSubscription.objects.create(
        tenant=hotel, plan=plan, status=SubscriptionStatus.ACTIVE,
    )
    site = Site.objects.create(tenant=hotel, name="Property")
    frontdesk = Outlet.objects.create(
        site=site, name="Reception", outlet_type=OutletType.LODGING_FRONT_DESK,
    )
    user = User.objects.create_user(
        email="release-hotel@example.test", password="SafePass!2026",
    )
    member = Membership.objects.create(
        user=user, tenant=hotel, role=MembershipRole.OWNER,
    )

    modules = get_tenant_staff_modules(hotel, outlet=frontdesk)
    nav = staff_nav_visibility_scoped(
        member, modules=modules, tenant=hotel, outlet=frontdesk,
    )
    assert "delivery" not in modules
    assert nav.lodging
    assert not nav.delivery
