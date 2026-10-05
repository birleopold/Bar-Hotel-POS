"""Staff nav module keys, tenant enablement, and role × module visibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from apps.accounts.models import Membership, MembershipRole
from apps.tenants.models import (
    Outlet,
    SubscriptionStatus,
    Tenant,
    TenantFeatureEntitlement,
    TenantOutletModulePolicy,
    TenantSettings,
    TenantSubscription,
)

STAFF_MODULE_KEYS: FrozenSet[str] = frozenset(
    {
        "pos",
        "kitchen",
        "promotions",
        "inventory",
        "purchasing",
        "lodging",
        "events",
        "finance",
        "workspace",
    }
)
DEFAULT_STAFF_MODULES: FrozenSet[str] = STAFF_MODULE_KEYS

# Order for workspace UI and forms (key, label).
STAFF_MODULE_CHOICES: tuple[tuple[str, str], ...] = (
    ("pos", "Point of sale"),
    ("kitchen", "Prep queue (KDS)"),
    ("promotions", "Offers"),
    ("inventory", "Stock"),
    ("purchasing", "Purchasing"),
    ("lodging", "Lodging & rooms"),
    ("events", "Events & spaces"),
    ("finance", "Finance (income & expenses)"),
    ("workspace", "Workspace & team"),
)


def get_tenant_staff_modules(
    tenant: Tenant,
    *,
    outlet: Outlet | None = None,
    outlet_type: str | None = None,
) -> FrozenSet[str]:
    """Modules enabled for this tenant, optionally scoped by active outlet/outlet type."""
    return resolve_effective_staff_modules(tenant, outlet=outlet, outlet_type=outlet_type)


def resolve_effective_staff_modules(
    tenant: Tenant,
    *,
    outlet: Outlet | None = None,
    outlet_type: str | None = None,
) -> FrozenSet[str]:
    """Resolve modules from tenant settings, plan defaults, entitlements, and optional outlet policy."""
    # Business profile is the tenant's product boundary; module and plan grants
    # may narrow it but must not widen it to unrelated product lines.
    try:
        settings = tenant.settings
    except TenantSettings.DoesNotExist:
        # Older tenants can legitimately predate TenantSettings. Preserve the
        # established defaults for those tenants; an explicitly saved invalid
        # profile remains fail-closed below.
        from apps.tenants.business_lines import DEFAULT_MODULES_ALL

        configured_line_modules = frozenset(DEFAULT_MODULES_ALL)
        settings_modules = configured_line_modules
    else:
        from apps.tenants.business_lines import DEFAULT_MODULES_ALL, modules_for_business_lines, normalize_business_lines

        raw_lines = settings.business_lines if isinstance(settings.business_lines, list) else None
        lines = normalize_business_lines(raw_lines)
        if raw_lines and not lines:
            # A saved but invalid profile is a configuration error; do not grant broad access.
            return frozenset()
        # Empty profile predates business-line scoping and remains the documented
        # legacy tenant state. A configured profile can never be widened by modules.
        configured_line_modules = frozenset(
            modules_for_business_lines(lines) if lines else DEFAULT_MODULES_ALL
        )
        raw = settings.enabled_staff_modules
        if not isinstance(raw, list):
            settings_modules = frozenset()
        elif not raw:
            settings_modules = configured_line_modules
        else:
            settings_modules = STAFF_MODULE_KEYS & frozenset(str(x) for x in raw)
        settings_modules = settings_modules & configured_line_modules

    # Control-plane overlays are optional; if missing, preserve legacy behavior.
    try:
        sub = tenant.subscription
    except TenantSubscription.DoesNotExist:
        return settings_modules

    if sub.status in {SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED}:
        return frozenset()

    raw_plan = sub.plan.included_modules if isinstance(sub.plan.included_modules, list) else []
    plan_modules = STAFF_MODULE_KEYS & frozenset(str(x) for x in raw_plan)
    if not plan_modules:
        return frozenset()
    effective = settings_modules & plan_modules
    # An empty intersection means the tenant's selected services are not included
    # in its plan. Fail closed rather than unioning unrelated modules into access.

    # Per-module tenant entitlement overrides apply last.
    overrides = TenantFeatureEntitlement.objects.filter(tenant=tenant).values_list(
        "module_key",
        "is_enabled",
    )
    for module_key, is_enabled in overrides:
        if module_key not in STAFF_MODULE_KEYS:
            continue
        if is_enabled:
            # An entitlement may widen a plan, but never the configured business profile.
            if module_key in configured_line_modules:
                effective = effective | {module_key}
        else:
            effective = frozenset(m for m in effective if m != module_key)
    scoped_outlet_type = (outlet_type or (outlet.outlet_type if outlet is not None else "")).strip()
    if scoped_outlet_type:
        policy = TenantOutletModulePolicy.objects.filter(
            tenant=tenant,
            outlet_type=scoped_outlet_type,
            is_active=True,
        ).first()
        if policy is not None:
            raw_policy = policy.enabled_modules if isinstance(policy.enabled_modules, list) else []
            policy_modules = STAFF_MODULE_KEYS & frozenset(str(x) for x in raw_policy)
            effective = frozenset(m for m in effective if m in policy_modules)
    return frozenset(effective)


def initial_staff_modules_for_form(tenant: Tenant) -> list[str]:
    """Checkbox initial values: stored list or all modules in display order."""
    try:
        from apps.tenants.business_lines import DEFAULT_MODULES_ALL, modules_for_business_lines, normalize_business_lines

        raw_lines = tenant.settings.business_lines if isinstance(tenant.settings.business_lines, list) else None
        lines = normalize_business_lines(raw_lines)
    except TenantSettings.DoesNotExist:
        raw_lines = None
        lines = []
    line_modules = set(
        modules_for_business_lines(lines) if lines else (DEFAULT_MODULES_ALL if raw_lines == [] else [])
    )
    raw = tenant_stored_module_list_raw(tenant)
    if raw:
        order = [k for k, _ in STAFF_MODULE_CHOICES]
        return sorted((k for k in raw if k in line_modules), key=lambda x: order.index(x) if x in order else 99)
    enabled = line_modules
    order = [k for k, _ in STAFF_MODULE_CHOICES]
    return [k for k in order if k in enabled]


def tenant_stored_module_list_raw(tenant: Tenant) -> list[str] | None:
    """
    Return the raw enabled_staff_modules list from settings if non-empty and valid,
    or None when the tenant effectively uses the default (all modules).
    """
    try:
        raw = tenant.settings.enabled_staff_modules
    except TenantSettings.DoesNotExist:
        return None
    if not isinstance(raw, list) or len(raw) == 0:
        return None
    cleaned = [str(x) for x in raw if str(x) in STAFF_MODULE_KEYS]
    return cleaned


@dataclass(frozen=True, slots=True)
class StaffNavVisibility:
    """Which staff nav areas and deep links are shown for this membership + tenant modules."""

    orders: bool = False
    tables: bool = False
    kitchen: bool = False
    menu: bool = False
    promotions: bool = False
    sales: bool = False
    offline_sync: bool = False
    inventory: bool = False
    purchasing: bool = False
    lodging: bool = False
    events: bool = False
    finance: bool = False
    workspace: bool = False


def staff_nav_visibility(membership: Membership, modules: FrozenSet[str]) -> StaffNavVisibility:
    M = MembershipRole
    r = membership.role

    orders = tables = menu = sales = offline_sync = False
    if "pos" in modules:
        floor_pos = {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.OUTLET_MANAGER,
            M.SERVER,
            M.BARTENDER,
            M.ACCOUNTANT,
            M.FRONT_DESK,
        }
        if r in floor_pos:
            orders = True
            tables = True
        menu_roles = floor_pos | {M.KITCHEN}
        if r in menu_roles:
            menu = True
        sales_roles = {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.OUTLET_MANAGER,
            M.FRONT_DESK,
            M.ACCOUNTANT,
            M.STOREKEEPER,
        }
        if r in sales_roles:
            sales = True
            offline_sync = True

    kitchen = False
    if "kitchen" in modules:
        kitchen = r in {
            M.KITCHEN,
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.OUTLET_MANAGER,
            M.SERVER,
            M.BARTENDER,
        }

    promotions = False
    if "promotions" in modules:
        promotions = r in {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.OUTLET_MANAGER,
            M.ACCOUNTANT,
        }

    inventory = purchasing = False
    if "inventory" in modules:
        inventory = r in {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.OUTLET_MANAGER,
            M.STOREKEEPER,
            M.ACCOUNTANT,
        }
    if "purchasing" in modules:
        purchasing = r in {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.OUTLET_MANAGER,
            M.STOREKEEPER,
            M.ACCOUNTANT,
        }

    lodging = False
    if "lodging" in modules:
        lodging = r in {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.FRONT_DESK,
            M.ACCOUNTANT,
            M.OUTLET_MANAGER,
        }

    events = False
    if "events" in modules:
        events = r in {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.OUTLET_MANAGER,
            M.FRONT_DESK,
            M.ACCOUNTANT,
        }

    finance = False
    if "finance" in modules:
        finance = r in {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.ACCOUNTANT,
        }

    workspace = False
    if "workspace" in modules:
        workspace = r in {
            M.OWNER,
            M.TENANT_ADMIN,
            M.SITE_MANAGER,
            M.OUTLET_MANAGER,
            M.ACCOUNTANT,
        }

    return StaffNavVisibility(
        orders=orders,
        tables=tables,
        kitchen=kitchen,
        menu=menu,
        promotions=promotions,
        sales=sales,
        offline_sync=offline_sync,
        inventory=inventory,
        purchasing=purchasing,
        lodging=lodging,
        events=events,
        finance=finance,
        workspace=workspace,
    )


def staff_nav_capability_allowed(vis: StaffNavVisibility, cap: str | tuple[str, ...]) -> bool:
    if isinstance(cap, tuple):
        return any(getattr(vis, name, False) for name in cap)
    return getattr(vis, cap, False)
