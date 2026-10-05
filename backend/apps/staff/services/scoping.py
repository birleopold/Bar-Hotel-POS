from __future__ import annotations

from apps.accounts.models import Membership
from apps.tenants.business_lines import normalize_business_lines
from apps.tenants.models import Outlet, Tenant, TenantSettings

from .modules import StaffNavVisibility, staff_nav_visibility


def _caps_for_outlet_type(outlet_type: str) -> set[str]:
    ot = (outlet_type or "").strip()
    if ot in {"restaurant", "bar", "lounge", "cafeteria"}:
        return {
            "orders",
            "tables",
            "kitchen",
            "menu",
            "promotions",
            "sales",
            "inventory",
            "purchasing",
            "finance",
            "workspace",
        }
    if ot in {"retail", "supermarket"}:
        return {
            "orders",
            "menu",
            "promotions",
            "sales",
            "inventory",
            "purchasing",
            "finance",
            "workspace",
        }
    if ot == "lodging_front_desk":
        return {
            "lodging",
            "orders",
            "sales",
            "promotions",
            "finance",
            "workspace",
        }
    if ot == "event_space":
        return {
            "events",
            "orders",
            "sales",
            "promotions",
            "finance",
            "workspace",
        }
    if ot == "service":
        return {"orders", "sales", "finance", "workspace"}
    return {
        "orders",
        "tables",
        "kitchen",
        "menu",
        "promotions",
        "sales",
        "inventory",
        "purchasing",
        "lodging",
        "events",
        "finance",
        "workspace",
    }


def _caps_for_business_lines(lines: list[str]) -> set[str]:
    s = set(normalize_business_lines(lines))
    if not s:
        # Empty profile is the legacy pre-business-lines state. Capability
        # checks below still intersect this with the member role, enabled modules,
        # and selected outlet policy.
        return set(_caps_for_outlet_type(""))
    caps: set[str] = {"finance", "workspace"}
    if s & {"bar", "lounge", "restaurant", "cafeteria"}:
        caps |= {
            "orders",
            "tables",
            "menu",
            "promotions",
            "sales",
            "inventory",
            "purchasing",
        }
    if s & {"bar", "lounge", "restaurant", "cafeteria", "kitchen"}:
        caps |= {"kitchen", "menu", "inventory", "purchasing"}
    if s & {"retail", "supermarket"}:
        caps |= {
            "orders",
            "menu",
            "promotions",
            "sales",
            "inventory",
            "purchasing",
        }
    if "lodging" in s:
        caps |= {"lodging", "orders", "sales", "promotions"}
    if "events" in s:
        caps |= {"events", "orders", "sales", "promotions"}
    if "services" in s:
        caps |= {"orders", "sales"}
    return caps


def staff_nav_visibility_scoped(
    membership: Membership,
    *,
    modules,
    tenant: Tenant,
    outlet: Outlet | None = None,
) -> StaffNavVisibility:
    base = staff_nav_visibility(membership, modules)

    try:
        settings_obj = tenant.settings
    except TenantSettings.DoesNotExist:
        # Pre-business-line tenants are legacy workspaces and keep the broad
        # capability map, constrained by role, plan modules, and outlet policy.
        lines: list[str] = []
    else:
        lines = list(getattr(settings_obj, "business_lines", None) or [])

    allowed = _caps_for_business_lines(lines)
    if outlet is not None:
        # An active POS section narrows section-specific tools, while property-level
        # workflows remain reachable (front desk, events, finance, workspace).
        property_caps = {"lodging", "events", "finance", "workspace"}
        outlet_caps = _caps_for_outlet_type(outlet.outlet_type)
        allowed = (allowed & outlet_caps) | (allowed & property_caps)
        if "pos" not in modules:
            allowed -= {"orders", "tables", "menu", "sales", "promotions", "offline_sync"}
        if "kitchen" not in modules:
            allowed.discard("kitchen")
        if "inventory" not in modules:
            allowed.discard("inventory")
        if "purchasing" not in modules:
            allowed.discard("purchasing")
        if "lodging" not in modules:
            allowed.discard("lodging")
        if "events" not in modules:
            allowed.discard("events")
        if "finance" not in modules:
            allowed.discard("finance")
        if "workspace" not in modules:
            allowed.discard("workspace")
    else:
        module_caps = set()
        module_to_caps = {
            "pos": {"orders", "tables", "menu", "sales", "promotions", "offline_sync"},
            "kitchen": {"kitchen"},
            "inventory": {"inventory"},
            "purchasing": {"purchasing"},
            "lodging": {"lodging"},
            "events": {"events"},
            "finance": {"finance"},
            "workspace": {"workspace"},
        }
        for module_key in modules:
            module_caps.update(module_to_caps.get(module_key, set()))
        allowed &= module_caps

    return StaffNavVisibility(
        orders=base.orders and "orders" in allowed,
        tables=base.tables and "tables" in allowed,
        kitchen=base.kitchen and "kitchen" in allowed,
        menu=base.menu and "menu" in allowed,
        promotions=base.promotions and "promotions" in allowed,
        sales=base.sales and "sales" in allowed,
        offline_sync=base.offline_sync and "sales" in allowed,
        inventory=base.inventory and "inventory" in allowed,
        purchasing=base.purchasing and "purchasing" in allowed,
        lodging=base.lodging and "lodging" in allowed,
        events=base.events and "events" in allowed,
        finance=base.finance and "finance" in allowed,
        workspace=base.workspace and "workspace" in allowed,
    )
