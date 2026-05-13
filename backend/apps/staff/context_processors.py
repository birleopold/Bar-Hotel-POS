"""Expose tenant theme on staff routes when ``request.tenant`` is set (session middleware)."""

from __future__ import annotations

from apps.tenants.models import TenantSettings


def staff_branding(request):
    path = getattr(request, "path", "") or ""
    if not path.startswith("/staff") and not path.startswith("/console"):
        return {"tenant_settings": None}
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return {"tenant_settings": None}
    try:
        return {"tenant_settings": TenantSettings.objects.get(tenant=tenant)}
    except TenantSettings.DoesNotExist:
        return {"tenant_settings": None}


def staff_nav(request):
    """Outlet list, site list, role + tenant-module nav flags for staff chrome."""
    out = {
        "staff_nav": None,
        "staff_nav_outlets": [],
        "staff_nav_outlet": None,
        "staff_show_ops_nav": False,
        "staff_all_outlets": False,
        "staff_lodging_sites": [],
        "staff_lodging_site": None,
        "staff_show_lodging_nav": False,
        "staff_show_workspace_nav": False,
        "staff_quick_primary": None,
        "staff_show_console_entry": False,
    }
    path = getattr(request, "path", "") or ""
    if not path.startswith("/staff"):
        return out
    m = getattr(request, "tenant_membership", None)
    t = getattr(request, "tenant", None)
    if not request.user.is_authenticated:
        return out
    from apps.console.mixins import membership_can_manage_org_console, user_is_platform_operator

    out["staff_show_console_entry"] = user_is_platform_operator(request.user) or (
        m is not None and membership_can_manage_org_console(m)
    )
    if not m or not t:
        return out
    from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
    from .services import (
        get_tenant_staff_modules,
        resolve_staff_outlet,
        resolve_staff_site,
        sites_visible_for_membership,
        staff_accessible_outlets,
        staff_nav_visibility_scoped,
    )

    outlets = staff_accessible_outlets(m)
    out["staff_nav_outlets"] = outlets
    current_outlet = resolve_staff_outlet(request, outlets)
    out["staff_nav_outlet"] = current_outlet
    out["staff_all_outlets"] = request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
    modules = get_tenant_staff_modules(t, outlet=current_outlet)
    vis = staff_nav_visibility_scoped(m, modules=modules, tenant=t, outlet=current_outlet)
    out["staff_nav"] = vis

    pos_shell = (
        ("pos" in modules and (vis.orders or vis.tables or vis.menu or vis.sales))
        or ("kitchen" in modules and vis.kitchen)
    )
    out["staff_show_ops_nav"] = bool(outlets) and pos_shell

    sites = sites_visible_for_membership(m)
    out["staff_lodging_sites"] = sites
    out["staff_lodging_site"] = resolve_staff_site(request, sites)
    out["staff_show_lodging_nav"] = bool(sites) and vis.lodging
    out["staff_show_workspace_nav"] = vis.workspace

    primary: str | None = None
    for name in (
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
    ):
        if getattr(vis, name, False):
            primary = name
            break
    if primary is None and vis.workspace:
        primary = "workspace"
    out["staff_quick_primary"] = primary
    return out
