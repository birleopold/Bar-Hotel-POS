"""Membership-scoped sites, outlets, and line-role outlet filtering."""

from __future__ import annotations

import uuid

from apps.accounts.models import Membership, MembershipRole
from apps.tenants.business_lines import normalize_business_lines, outlet_types_for_business_lines
from apps.tenants.models import Outlet, OutletType, Site, TenantSettings


def membership_queryset_for(user):
    return (
        Membership.objects.filter(user=user, is_active=True)
        .select_related("tenant")
        .order_by("tenant__name")
    )


def _profile_outlet_types(membership: Membership) -> set[str] | None:
    """Return configured outlet types; None means a broken/missing profile."""
    try:
        raw = membership.tenant.settings.business_lines
    except TenantSettings.DoesNotExist:
        # Tenants created before TenantSettings was introduced are legacy too.
        # Keep their existing role/site scope instead of blocking every outlet.
        return set()
    if raw == []:
        return set()  # legacy tenant: outlet type and role still constrain access
    lines = normalize_business_lines(raw if isinstance(raw, list) else None)
    if not lines:
        return None
    return set(outlet_types_for_business_lines(lines))


def sites_visible_for_membership(membership: Membership) -> list[Site]:
    qs = Site.objects.filter(tenant=membership.tenant, is_active=True)
    if membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
        qs = qs.filter(pk__in=membership.sites.values_list("pk", flat=True))
    elif membership.sites.exists():
        qs = qs.filter(pk__in=membership.sites.values_list("pk", flat=True))
    allowed_types = _profile_outlet_types(membership)
    if allowed_types is None:
        qs = qs.none()
    elif allowed_types:
        qs = qs.filter(outlets__outlet_type__in=allowed_types).distinct()
    if membership.role == MembershipRole.CLEANER:
        qs = qs.filter(
            outlets__outlet_type=OutletType.LODGING_FRONT_DESK,
            outlets__is_active=True,
        )
    return list(qs.order_by("name"))


def outlets_visible_for_site(membership: Membership, site: Site) -> list[Outlet]:
    if site.tenant_id != membership.tenant_id:
        return []
    if membership.role == MembershipRole.CLEANER:
        return []
    qs = Outlet.objects.filter(site=site, site__tenant=membership.tenant, is_active=True)
    if membership.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
        if membership.outlets.exists():
            qs = qs.filter(pk__in=membership.outlets.values_list("pk", flat=True))
    elif membership.role == MembershipRole.SITE_MANAGER:
        pass
    elif membership.outlets.exists():
        qs = qs.filter(pk__in=membership.outlets.values_list("pk", flat=True))
    allowed = ROLE_OUTLET_TYPES.get(membership.role)
    if allowed is not None:
        qs = qs.filter(outlet_type__in=allowed)
    allowed_types = _profile_outlet_types(membership)
    if allowed_types is None:
        return []
    if allowed_types:
        qs = qs.filter(outlet_type__in=allowed_types)
    return list(qs.order_by("name"))


def accessible_outlets_flat(membership: Membership) -> list[Outlet]:
    """All outlets this membership may use, ordered by site then outlet name."""
    if membership.role == MembershipRole.CLEANER:
        return []
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
            OutletType.SERVICE,
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
            OutletType.SERVICE,
        },
    ),
}

ROLE_OUTLET_TYPES: dict[str, frozenset[str]] = {
    MembershipRole.BARTENDER: LINE_ROLE_OUTLET_TYPES[MembershipRole.BARTENDER],
    MembershipRole.SERVER: LINE_ROLE_OUTLET_TYPES[MembershipRole.SERVER],
    MembershipRole.KITCHEN: LINE_ROLE_OUTLET_TYPES[MembershipRole.KITCHEN],
    MembershipRole.STOREKEEPER: frozenset(
        {OutletType.RESTAURANT, OutletType.BAR, OutletType.LOUNGE, OutletType.CAFETERIA, OutletType.RETAIL, OutletType.SUPERMARKET}
    ),
    MembershipRole.FRONT_DESK: frozenset({OutletType.LODGING_FRONT_DESK, OutletType.EVENT_SPACE}),
    MembershipRole.OUTLET_MANAGER: frozenset(OutletType),
    MembershipRole.SITE_MANAGER: frozenset(OutletType),
    MembershipRole.ACCOUNTANT: frozenset(OutletType),
    MembershipRole.CLEANER: frozenset({OutletType.LODGING_FRONT_DESK}),
}


def staff_accessible_outlets(membership: Membership) -> list[Outlet]:
    """
    Outlets for staff POS flows, ordered by site then name.

    Line roles (bartender, server, kitchen) only see outlet types that match their
    typical work area so bar staff are not switched into restaurant-only outlets.
    """
    if membership.role == MembershipRole.CLEANER:
        return []
    base = accessible_outlets_flat(membership)
    business_types = _profile_outlet_types(membership)
    if business_types is None:
        base = []
    elif business_types:
        base = [o for o in base if o.outlet_type in business_types]
    allowed = ROLE_OUTLET_TYPES.get(membership.role)
    if allowed is None:
        return base
    return [o for o in base if o.outlet_type in allowed]


def staff_outlet_allowed_for_membership(membership: Membership, outlet_id: uuid.UUID) -> bool:
    """Whether this membership may use the outlet in staff POS flows (includes role/outlet-type rules)."""
    return any(o.id == outlet_id for o in staff_accessible_outlets(membership))
