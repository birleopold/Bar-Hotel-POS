from __future__ import annotations

import uuid

from django.db.models import QuerySet

from apps.accounts.models import Membership
from apps.tenants.models import Outlet


def membership_outlet_ids(membership: Membership) -> list[uuid.UUID]:
    """Outlet UUIDs the membership may use (empty M2M = all tenant outlets)."""
    base = Outlet.objects.filter(site__tenant_id=membership.tenant_id, is_active=True)
    if membership.sites.exists():
        base = base.filter(site_id__in=membership.sites.values_list("pk", flat=True))
    if membership.outlets.exists():
        return list(
            base.filter(pk__in=membership.outlets.values_list("pk", flat=True)).values_list(
                "pk", flat=True
            )
        )
    return list(base.values_list("pk", flat=True))


def membership_outlets_qs(membership: Membership) -> QuerySet[Outlet]:
    ids = membership_outlet_ids(membership)
    return Outlet.objects.filter(pk__in=ids).select_related("site")


def outlet_belongs_to_membership(membership: Membership, outlet_id: uuid.UUID) -> bool:
    return outlet_id in membership_outlet_ids(membership)
