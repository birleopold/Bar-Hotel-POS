"""
Staff Workbench: role- and module-aware navigation playbook for the UI.
Maps every operational area to url names; templates only render visible rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.urls import NoReverseMatch, reverse

from apps.accounts.models import MembershipRole

if TYPE_CHECKING:
    from apps.staff.services.modules import StaffNavVisibility


@dataclass(frozen=True, slots=True)
class WorkbenchLink:
    label: str
    url: str
    hint: str = ""
    emphasis: bool = False  # primary CTA styling


@dataclass(frozen=True, slots=True)
class WorkbenchSection:
    key: str
    title: str
    subtitle: str
    links: tuple[WorkbenchLink, ...]


def _u(name: str, **kwargs) -> str:
    try:
        return reverse(name, kwargs=kwargs) if kwargs else reverse(name)
    except NoReverseMatch:
        return "#"


ROLE_AT_WORK: dict[str, tuple[str, ...]] = {
    MembershipRole.OWNER: ("Full workspace access.",),
    MembershipRole.TENANT_ADMIN: ("Admin — setup, team, operations.",),
    MembershipRole.SITE_MANAGER: ("Multi-branch — sales, stock, people.",),
    MembershipRole.OUTLET_MANAGER: ("Section lead — floor, prep, stock.",),
    MembershipRole.FRONT_DESK: ("Front desk — stays, folios, rooms.",),
    MembershipRole.SERVER: ("Service — orders, tables, handoff.",),
    MembershipRole.BARTENDER: ("Bar — tabs, drinks, prep handoff.",),
    MembershipRole.KITCHEN: ("Kitchen — prep queue & handoff.",),
    MembershipRole.STOREKEEPER: ("Stock — receiving, stock take, POs.",),
    MembershipRole.ACCOUNTANT: ("Reports — read-only summaries.",),
    MembershipRole.CLEANER: ("Housekeeping — update room readiness at assigned branches.",),
}


def build_workbench_playbook(
    *,
    vis: StaffNavVisibility,
    modules: frozenset[str],
    show_lodging_nav: bool,
    show_ops_nav: bool,
    membership_role: str,
) -> tuple[WorkbenchSection, ...]:
    """Return visible sections with links; mirrors staff nav capabilities + modules."""
    R = membership_role
    can_manage_offers = R in {
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
    }
    sections: list[WorkbenchSection] = []

    # —— Sales & floor (POS) ——
    if "pos" in modules:
        links: list[WorkbenchLink] = []
        if vis.orders:
            links.append(
                WorkbenchLink(
                    "Orders",
                    _u("staff-orders"),
                    "",
                    emphasis=True,
                )
            )
            links.append(
                WorkbenchLink(
                    "Quick order",
                    _u("staff-order-quick-create"),
                    "",
                )
            )
            if show_ops_nav:
                links.append(
                    WorkbenchLink(
                        "Offline queue",
                        _u("staff-offline-queue"),
                        "Sync / replay pending offline actions.",
                    )
                )
        if vis.orders and show_ops_nav:
            links.append(
                WorkbenchLink(
                    "Shifts",
                    _u("staff-pos-shifts"),
                    "",
                )
            )
        if vis.tables:
            links.append(
                WorkbenchLink(
                    "Tables",
                    _u("staff-tables"),
                    "",
                )
            )
            links.append(
                WorkbenchLink(
                    "New table",
                    _u("staff-table-create"),
                    "",
                )
            )
        if vis.menu:
            links.append(
                WorkbenchLink(
                    "Items",
                    _u("staff-menu"),
                    "",
                )
            )
        if links:
            sections.append(
                WorkbenchSection(
                    key="sales_floor",
                    title="Sales & floor",
                    subtitle="POS, tables, catalog.",
                    links=tuple(links),
                )
            )

    # —— Prep queue (KDS) ——
    if "kitchen" in modules and vis.kitchen:
        sections.append(
            WorkbenchSection(
                key="prep",
                title="Prep",
                subtitle="Kitchen / bar queue.",
                links=(
                    WorkbenchLink(
                        "Prep queue",
                        _u("staff-kds"),
                        "",
                        emphasis=True,
                    ),
                ),
            )
        )

    # —— Offers ——
    if "promotions" in modules and vis.promotions:
        offer_links = [
            WorkbenchLink(
                "Offers",
                _u("staff-promotions"),
                "",
            )
        ]
        if can_manage_offers:
            offer_links += (
                WorkbenchLink(
                    "New offer",
                    _u("staff-promotion-create"),
                    "",
                ),
            )
        sections.append(
            WorkbenchSection(
                key="offers",
                title="Offers",
                subtitle="Discounts at POS.",
                links=tuple(offer_links),
            )
        )

    # —— Reports ——
    if "pos" in modules and vis.sales:
        sections.append(
            WorkbenchSection(
                key="reports",
                title="Reports",
                subtitle="Sales & section splits.",
                links=(
                    WorkbenchLink(
                        "Sales",
                        _u("staff-sales"),
                        "",
                        emphasis=True,
                    ),
                ),
            )
        )

    # —— Stock ——
    if "inventory" in modules and vis.inventory:
        sections.append(
            WorkbenchSection(
                key="stock",
                title="Stock",
                subtitle="On-hand, ledger, stock take.",
                links=(
                    WorkbenchLink(
                        "On hand",
                        _u("staff-inventory-balances"),
                        "",
                        emphasis=True,
                    ),
                    WorkbenchLink("Ledger", _u("staff-inventory-movements"), ""),
                    WorkbenchLink(
                        "Stock movement",
                        _u("staff-inventory-movement-create"),
                        "",
                    ),
                    WorkbenchLink(
                        "CSV upload",
                        _u("staff-inventory-movement-upload"),
                        "",
                    ),
                    WorkbenchLink(
                        "Transfer",
                        _u("staff-inventory-transfer"),
                        "",
                    ),
                    WorkbenchLink("Stock take", _u("staff-inventory-counts"), ""),
                    WorkbenchLink(
                        "New stock take",
                        _u("staff-inventory-count-create"),
                        "",
                    ),
                ),
            )
        )

    # —— Purchasing ——
    if "purchasing" in modules and vis.purchasing:
        sections.append(
            WorkbenchSection(
                key="buying",
                title="Purchasing",
                subtitle="POs & suppliers.",
                links=(
                    WorkbenchLink(
                        "Purchase orders",
                        _u("staff-purchasing-orders"),
                        "",
                        emphasis=True,
                    ),
                    WorkbenchLink(
                        "New PO",
                        _u("staff-purchasing-order-create"),
                        "",
                    ),
                    WorkbenchLink("Suppliers", _u("staff-purchasing-suppliers"), ""),
                    WorkbenchLink(
                        "New supplier",
                        _u("staff-purchasing-supplier-create"),
                        "",
                    ),
                ),
            )
        )

    # —— Lodging ——
    if show_lodging_nav and vis.lodging:
        sections.append(
            WorkbenchSection(
                key="lodging",
                title="Lodging",
                subtitle="Stays, folios, rooms.",
                links=(
                    WorkbenchLink(
                        "Reservations",
                        _u("staff-lodging-reservations"),
                        "",
                        emphasis=True,
                    ),
                    WorkbenchLink(
                        "New stay",
                        _u("staff-lodging-reservation-create"),
                        "",
                    ),
                    WorkbenchLink("Folios", _u("staff-lodging-folios"), ""),
                    WorkbenchLink("Rooms", _u("staff-lodging-rooms"), ""),
                    WorkbenchLink("Tape", _u("staff-lodging-tape"), "14-night room occupancy grid."),
                    WorkbenchLink(
                        "Housekeeping",
                        _u("staff-lodging-housekeeping"),
                        "Room clean / dirty / inspected.",
                    ),
                    WorkbenchLink("Maintenance", _u("staff-lodging-maintenance"), "Assign and resolve room repairs."),
                    WorkbenchLink("Room types", _u("staff-lodging-room-types"), ""),
                ),
            )
        )

    # —— Events ——
    if "events" in modules and vis.events:
        sections.append(
            WorkbenchSection(
                key="events",
                title="Events",
                subtitle="Bookings & spaces.",
                links=(
                    WorkbenchLink(
                        "Bookings",
                        _u("staff-events-bookings"),
                        "",
                        emphasis=True,
                    ),
                    WorkbenchLink(
                        "Calendar",
                        _u("staff-events-calendar"),
                        "",
                    ),
                    WorkbenchLink(
                        "New booking",
                        _u("staff-events-booking-create"),
                        "",
                    ),
                    WorkbenchLink("Spaces", _u("staff-events-spaces"), ""),
                    WorkbenchLink(
                        "New space",
                        _u("staff-events-space-create"),
                        "",
                    ),
                ),
            )
        )

    # —— Finance (income & expenses, non-POS) ——
    if "finance" in modules and vis.finance:
        sections.append(
            WorkbenchSection(
                key="finance",
                title="Finance",
                subtitle="Income & expense outside POS.",
                links=(
                    WorkbenchLink(
                        "Income & expenses",
                        _u("staff-finance-entries"),
                        "",
                        emphasis=True,
                    ),
                    WorkbenchLink(
                        "New entry",
                        _u("staff-finance-entry-create"),
                        "",
                    ),
                    WorkbenchLink(
                        "New category",
                        _u("staff-finance-categories-new"),
                        "",
                    ),
                ),
            )
        )

    # —— Workspace (team & configuration) ——
    if "workspace" in modules and vis.workspace:
        sections.append(
            WorkbenchSection(
                key="workspace",
                title="Workspace",
                subtitle="Brand, modules, team.",
                links=(
                    WorkbenchLink(
                        "Branding",
                        _u("staff-workspace-branding"),
                        "",
                    ),
                    WorkbenchLink(
                        "Modules",
                        _u("staff-workspace-modules"),
                        "",
                        emphasis=True,
                    ),
                    WorkbenchLink(
                        "Integrations",
                        _u("staff-workspace-integrations"),
                        "",
                    ),
                    WorkbenchLink(
                        "New integration",
                        _u("staff-workspace-integration-create"),
                        "",
                    ),
                    WorkbenchLink(
                        "Team",
                        _u("staff-workspace-members"),
                        "",
                        emphasis=True,
                    ),
                    WorkbenchLink(
                        "New worker",
                        _u("staff-workspace-member-create"),
                        "",
                    ),
                    WorkbenchLink(
                        "Invites",
                        _u("staff-workspace-invites"),
                        "",
                    ),
                    WorkbenchLink(
                        "Send invite",
                        _u("staff-workspace-invite-create"),
                        "",
                    ),
                    WorkbenchLink(
                        "Activity",
                        _u("staff-workspace-audit"),
                        "",
                    ),
                ),
            )
        )

    cleaned: list[WorkbenchSection] = []
    for sec in sections:
        links = tuple(l for l in sec.links if l.url != "#")
        if links:
            cleaned.append(
                WorkbenchSection(key=sec.key, title=sec.title, subtitle=sec.subtitle, links=links)
            )
    return tuple(cleaned)


def role_at_work_copy(role: str) -> tuple[str, ...]:
    return ROLE_AT_WORK.get(role, ("Staff",))
