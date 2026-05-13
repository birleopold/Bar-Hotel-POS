"""
Action-first dashboard: ordered primary tasks for the signed-in role (Phase 3 staff UX).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, FrozenSet

from django.urls import NoReverseMatch, reverse

from apps.accounts.models import MembershipRole

if TYPE_CHECKING:
    from .modules import StaffNavVisibility


@dataclass(frozen=True, slots=True)
class StaffDashboardAction:
    label: str
    url: str
    variant: str  # "primary" | "secondary"
    hint: str = ""


_ACTION_DEFS: dict[str, tuple[str, str, str]] = {
    "orders": ("staff-orders", "Orders", ""),
    "tables": ("staff-tables", "Tables", ""),
    "kitchen": ("staff-kds", "Prep", ""),
    "menu": ("staff-menu", "Items", ""),
    "promotions": ("staff-promotions", "Offers", ""),
    "sales": ("staff-sales", "Sales", ""),
    "inventory": ("staff-inventory-balances", "Stock", ""),
    "purchasing": ("staff-purchasing-orders", "Purchasing", ""),
    "lodging": ("staff-lodging-reservations", "Rooms", ""),
    "events": ("staff-events-bookings", "Events", ""),
    "finance": ("staff-finance-entries", "Income & expenses", ""),
    "workspace": ("staff-workspace-branding", "Workspace", ""),
}


def _role_cap_order(role: str) -> list[str]:
    R = MembershipRole
    if role == R.ACCOUNTANT:
        return [
            "finance",
            "sales",
            "orders",
            "tables",
            "kitchen",
            "menu",
            "promotions",
            "inventory",
            "purchasing",
            "lodging",
            "events",
            "workspace",
        ]
    if role == R.KITCHEN:
        return [
            "kitchen",
            "orders",
            "menu",
            "tables",
            "inventory",
            "sales",
            "promotions",
            "purchasing",
            "lodging",
            "events",
            "finance",
            "workspace",
        ]
    if role in (R.SERVER, R.BARTENDER):
        return [
            "orders",
            "tables",
            "kitchen",
            "menu",
            "sales",
            "promotions",
            "inventory",
            "purchasing",
            "lodging",
            "events",
            "finance",
            "workspace",
        ]
    if role == R.STOREKEEPER:
        return [
            "inventory",
            "purchasing",
            "orders",
            "tables",
            "kitchen",
            "menu",
            "sales",
            "promotions",
            "lodging",
            "events",
            "finance",
            "workspace",
        ]
    if role == R.FRONT_DESK:
        return [
            "lodging",
            "orders",
            "tables",
            "events",
            "sales",
            "kitchen",
            "menu",
            "promotions",
            "inventory",
            "purchasing",
            "finance",
            "workspace",
        ]
    return [
        "orders",
        "sales",
        "finance",
        "tables",
        "kitchen",
        "menu",
        "inventory",
        "purchasing",
        "lodging",
        "events",
        "promotions",
        "workspace",
    ]


def _cap_visible(
    cap: str,
    *,
    vis: StaffNavVisibility,
    modules: FrozenSet[str],
    show_lodging_nav: bool,
    show_ops_nav: bool,
) -> bool:
    if not getattr(vis, cap, False):
        return False
    if cap == "lodging":
        return show_lodging_nav
    if cap in ("orders", "tables", "menu", "sales", "promotions"):
        return show_ops_nav or cap == "promotions"
    if cap == "kitchen":
        return show_ops_nav and "kitchen" in modules
    if cap == "promotions":
        return "promotions" in modules
    if cap == "inventory":
        return "inventory" in modules
    if cap == "purchasing":
        return "purchasing" in modules
    if cap == "events":
        return "events" in modules
    if cap == "finance":
        return "finance" in modules
    if cap == "workspace":
        return "workspace" in modules
    return True


def staff_dashboard_actions(
    *,
    membership,
    vis: StaffNavVisibility,
    modules: FrozenSet[str],
    show_lodging_nav: bool,
    show_ops_nav: bool,
    action_overrides: dict[str, tuple[str, str]] | None = None,
) -> tuple[list[StaffDashboardAction], list[StaffDashboardAction]]:
    order = _role_cap_order(membership.role)
    primary: list[StaffDashboardAction] = []
    seen_urls: set[str] = set()
    overrides = action_overrides or {}

    for cap in order:
        if cap not in _ACTION_DEFS:
            continue
        if not _cap_visible(
            cap,
            vis=vis,
            modules=modules,
            show_lodging_nav=show_lodging_nav,
            show_ops_nav=show_ops_nav,
        ):
            continue
        url_name, label, hint = _ACTION_DEFS[cap]
        if cap in overrides:
            label, hint = overrides[cap]
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        primary.append(StaffDashboardAction(label=label, url=url, variant="primary", hint=hint))

    top = primary[:5]
    overflow = primary[5:]

    secondary_specs = [
        ("staff-inventory-movement-create", "Stock movement", ""),
        ("staff-inventory-count-create", "Stock take", ""),
        ("staff-purchasing-order-create", "New PO", ""),
        ("staff-lodging-reservation-create", "New stay", ""),
        ("staff-lodging-folios", "Folios", ""),
        ("staff-events-booking-create", "New booking", ""),
        ("staff-finance-entry-create", "Income or expense", ""),
        ("staff-workspace-members", "Team", ""),
    ]
    secondary: list[StaffDashboardAction] = []
    for url_name, label, hint in secondary_specs:
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            continue
        if url in seen_urls:
            continue
        # Only show ops extras when user has relevant nav
        if "inventory" in url_name and not vis.inventory:
            continue
        if "purchasing" in url_name and not vis.purchasing:
            continue
        if "lodging" in url_name and not (vis.lodging and show_lodging_nav):
            continue
        if "events" in url_name and not vis.events:
            continue
        if "finance" in url_name and not vis.finance:
            continue
        if "workspace" in url_name and not vis.workspace:
            continue
        seen_urls.add(url)
        secondary.append(StaffDashboardAction(label=label, url=url, variant="secondary", hint=hint))

    for a in overflow:
        if a.url not in seen_urls:
            secondary.insert(0, a)
            seen_urls.add(a.url)

    return top, secondary[:10]
