"""Membership-scoped sites, outlets, and line-role outlet filtering."""

from __future__ import annotations

import uuid

from apps.accounts.models import Membership, MembershipRole
from apps.tenants.models import Outlet, OutletType, Site


def membership_queryset_for(user):
    return (
        Membership.objects.filter(user=user, is_active=True)
        .select_related("tenant")
        .order_by("tenant__name")
    )


def sites_visible_for_membership(membership: Membership) -> list[Site]:
    qs = Site.objects.filter(tenant=membership.tenant, is_active=True)
    if membership.sites.exists():
        qs = qs.filter(pk__in=membership.sites.values_list("pk", flat=True))
    return list(qs.order_by("name"))


def outlets_visible_for_site(membership: Membership, site: Site) -> list[Outlet]:
    qs = Outlet.objects.filter(site=site, is_active=True)
    if membership.outlets.exists():
        qs = qs.filter(pk__in=membership.outlets.values_list("pk", flat=True))
    return list(qs.order_by("name"))


def accessible_outlets_flat(membership: Membership) -> list[Outlet]:
    """All outlets this membership may use, ordered by site then outlet name."""
    out: list[Outlet] = []
    for site in sites_visible_for_membership(membership):
        out.extend(outlets_visible_for_site(membership, site))
    return out


LINE_ROLE_OUTLET_TYPES: dict[str, frozenset[str]] = {
    MembershipRole.BARTENDER: frozenset(
        {OutletType.RESTAURANT, OutletType.BAR, OutletType.LOUNGE, OutletType.CAFETERIA},
    ),
    MembershipRole.SERVER: frozenset(
        {
            OutletType.RESTAURANT,
            OutletType.BAR,
            OutletType.LOUNGE,
            OutletType.CAFETERIA,
            OutletType.RETAIL,
            OutletType.SUPERMARKET,
        },
    ),
    MembershipRole.KITCHEN: frozenset(
        {
            OutletType.RESTAURANT,
            OutletType.BAR,
            OutletType.LOUNGE,
            OutletType.CAFETERIA,
            OutletType.RETAIL,
            OutletType.SUPERMARKET,
        },
    ),
}


def staff_accessible_outlets(membership: Membership) -> list[Outlet]:
    """
    Outlets for staff POS flows, ordered by site then name.

    Line roles (bartender, server, kitchen) only see outlet types that match their
    typical work area so bar staff are not switched into restaurant-only outlets.
    """
    base = accessible_outlets_flat(membership)
    allowed = LINE_ROLE_OUTLET_TYPES.get(membership.role)
    if allowed is None:
        return base
    return [o for o in base if o.outlet_type in allowed]


def staff_outlet_allowed_for_membership(membership: Membership, outlet_id: uuid.UUID) -> bool:
    """Whether this membership may use the outlet in staff POS flows (includes role/outlet-type rules)."""
    return any(o.id == outlet_id for o in staff_accessible_outlets(membership))
