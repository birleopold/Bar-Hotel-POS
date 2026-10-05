from __future__ import annotations

import uuid

from django.db.models import QuerySet

from apps.accounts.models import Membership
from apps.accounts.models import MembershipRole
from apps.tenants.business_lines import normalize_business_lines, outlet_types_for_business_lines
from apps.tenants.models import Outlet
from apps.tenants.models import TenantSettings


def membership_outlet_ids(membership: Membership) -> list[uuid.UUID]:
    """Outlet UUIDs the membership may use; worker scope must be assigned explicitly."""
    base = Outlet.objects.filter(site__tenant_id=membership.tenant_id, is_active=True)
    try:
        raw_lines = membership.tenant.settings.business_lines
    except TenantSettings.DoesNotExist:
        # Pre-profile tenants retain their historical access boundary.
        raw_lines = []
    if not (isinstance(raw_lines, list) and not raw_lines):
        lines = normalize_business_lines(raw_lines if isinstance(raw_lines, list) else None)
        if not lines:
            return []
        allowed_types = outlet_types_for_business_lines(lines)
        if not allowed_types:
            return []
        base = base.filter(outlet_type__in=allowed_types)
    if membership.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
        if membership.sites.exists():
            base = base.filter(site_id__in=membership.sites.values_list("pk", flat=True))
        if membership.outlets.exists():
            base = base.filter(pk__in=membership.outlets.values_list("pk", flat=True))
    else:
        if not membership.sites.exists():
            return []
        base = base.filter(site_id__in=membership.sites.values_list("pk", flat=True))
        if membership.outlets.exists():
            base = base.filter(pk__in=membership.outlets.values_list("pk", flat=True))
    from apps.staff.services.membership import ROLE_OUTLET_TYPES

    role_types = ROLE_OUTLET_TYPES.get(membership.role)
    if role_types is not None:
        base = base.filter(outlet_type__in=role_types)
    return list(base.values_list("pk", flat=True))


def membership_outlets_qs(membership: Membership) -> QuerySet[Outlet]:
    ids = membership_outlet_ids(membership)
    return Outlet.objects.filter(pk__in=ids).select_related("site")


def outlet_belongs_to_membership(membership: Membership, outlet_id: uuid.UUID) -> bool:
    return outlet_id in membership_outlet_ids(membership)
