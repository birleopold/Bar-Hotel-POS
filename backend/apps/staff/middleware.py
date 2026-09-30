"""Attach ``request.tenant`` from session for browser staff UI (no ``X-Tenant-Id`` header)."""

from __future__ import annotations

import uuid
import time
from typing import Callable

from django.contrib.auth import logout
from django.http import HttpRequest
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from apps.accounts.models import Membership
from apps.tenants.models import Tenant

STAFF_SESSION_TENANT_KEY = "staff_tenant_id"
STAFF_SESSION_OUTLET_KEY = "staff_outlet_id"
# Session value meaning: show aggregated lists / all outlets (orders, sales).
STAFF_SESSION_OUTLET_ALL = "__all__"
# Active property (site) for lodging lists and front-desk flows.
STAFF_SESSION_SITE_KEY = "staff_site_id"


class StaffTerminalIdleMiddleware:
    """Enforce a server-side idle limit on PIN-enabled shared staff sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/staff/logout/":
            return self.get_response(request)
        if (request.user.is_authenticated and request.session.get("staff_pin_authenticated")
                and not request.path.startswith("/staff/")):
            return HttpResponseForbidden("Use your account password for other areas.")
        if not request.path.startswith("/staff/"):
            return self.get_response(request)
        if request.user.is_authenticated and request.session.get("staff_pin_session"):
            from .terminal import PIN_IDLE_SECONDS, mark_terminal

            now = int(time.time())
            last = request.session.get("staff_pin_last_activity", 0)
            membership = getattr(request, "tenant_membership", None)
            pairing_valid = True
            if request.session.get("staff_pin_pairing"):
                from .workstations import active_pairing
                pair = active_pairing(request, tenant_id=membership.tenant_id) if membership else None
                pairing_valid = pair is not None and str(pair.pk) == request.session["staff_pin_pairing"]
            credential_valid = (
                pairing_valid and
                membership is not None
                and bool(membership.staff_pin_hash)
                and request.session.get("staff_pin_credential") == membership.staff_pin_hash
            )
            if not credential_valid or not isinstance(last, int) or now - last >= PIN_IDLE_SECONDS:
                tenant_id = request.session.get(STAFF_SESSION_TENANT_KEY)
                outlet_id = request.session.get(STAFF_SESSION_OUTLET_KEY, "")
                logout(request)
                if request.path.startswith("/staff/"):
                    response = redirect("staff-terminal")
                    if tenant_id:
                        response = mark_terminal(response, tenant_id=tenant_id, outlet_id=outlet_id, request=request)
                    return response
                return HttpResponseForbidden("Staff terminal locked. Unlock in the staff workspace.")
            # Background polling is not a worker interaction. It must not keep
            # an unattended register unlocked indefinitely.
            if request.method not in {"GET", "HEAD"} or "text/html" in request.headers.get("Accept", ""):
                request.session["staff_pin_last_activity"] = now
        response = self.get_response(request)
        if request.path.startswith("/staff/"):
            response["Cache-Control"] = "private, no-store"
        return response


class StaffSessionTenantMiddleware:
    """
    For paths under ``/staff/`` (except login/logout), if the user is authenticated and
    ``request.session[staff_tenant_id]`` is set and valid, attach ``request.tenant`` and
    ``request.tenant_membership`` (same attributes as API tenant middleware).
    """

    def __init__(self, get_response: Callable[[HttpRequest], object]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        path = request.path
        if not path.startswith("/staff/") and not path.startswith("/console"):
            return self.get_response(request)
        if path == "/staff/terminal/" and not request.user.is_authenticated:
            from .terminal import terminal_scope

            scope = terminal_scope(request, validate_pairing=False)
            if scope is not None:
                request.tenant = Tenant.objects.filter(pk=scope[0], is_active=True).first()
            return self.get_response(request)
        if path.startswith("/staff/login") or path.startswith("/staff/logout"):
            return self.get_response(request)
        if not request.user.is_authenticated:
            return self.get_response(request)

        raw = request.session.get(STAFF_SESSION_TENANT_KEY)
        if not raw:
            return self.get_response(request)
        try:
            tenant_uuid = uuid.UUID(str(raw))
        except ValueError:
            return self.get_response(request)

        membership = (
            Membership.objects.filter(
                user=request.user,
                tenant_id=tenant_uuid,
                is_active=True,
            )
            .select_related("tenant")
            .first()
        )
        if membership is None:
            return self.get_response(request)

        request.tenant = membership.tenant
        request.tenant_membership = membership

        return self.get_response(request)
