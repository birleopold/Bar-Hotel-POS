"""Session-backed staff site / outlet selection."""

from __future__ import annotations

import uuid

from django.http import HttpRequest

from apps.tenants.models import Outlet, Site

from ..middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_SITE_KEY


def resolve_staff_site(request: HttpRequest, sites: list[Site]) -> Site | None:
    """Active site for lodging; defaults to first visible site when session unset or invalid."""
    if not sites:
        return None
    raw = request.session.get(STAFF_SESSION_SITE_KEY)
    if raw:
        try:
            uid = uuid.UUID(str(raw))
            for s in sites:
                if s.id == uid:
                    return s
        except ValueError:
            pass
    request.session[STAFF_SESSION_SITE_KEY] = str(sites[0].id)
    return sites[0]


def resolve_staff_outlet(request: HttpRequest, outlets: list[Outlet]) -> Outlet | None:
    """Active outlet, or ``None`` when session is set to all outlets."""
    if not outlets:
        return None
    raw = request.session.get(STAFF_SESSION_OUTLET_KEY)
    if raw == STAFF_SESSION_OUTLET_ALL:
        return None
    if raw:
        try:
            uid = uuid.UUID(str(raw))
            for o in outlets:
                if o.id == uid:
                    return o
        except ValueError:
            pass
    request.session[STAFF_SESSION_OUTLET_KEY] = str(outlets[0].id)
    return outlets[0]
