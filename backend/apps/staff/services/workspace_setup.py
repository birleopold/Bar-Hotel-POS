"""Detect whether a tenant still needs org setup (sites / outlets) in Console."""

from __future__ import annotations

from apps.tenants.models import Outlet, Site


def tenant_org_setup_incomplete(tenant) -> bool:
    """True when there are no active sites or no active outlets under active sites."""
    if not Site.objects.filter(tenant=tenant, is_active=True).exists():
        return True
    if not Outlet.objects.filter(
        site__tenant=tenant,
        site__is_active=True,
        is_active=True,
    ).exists():
        return True
    return False
