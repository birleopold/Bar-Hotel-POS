"""Attach ``request.tenant`` from session for browser staff UI (no ``X-Tenant-Id`` header)."""

from __future__ import annotations

import uuid
import time
from typing import Callable

from django.contrib.auth import logout
from django.db import connection, transaction
from django.conf import settings
from django.http import HttpRequest, HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import redirect

from apps.accounts.models import Membership
from apps.tenants.models import Tenant

STAFF_SESSION_TENANT_KEY = "staff_tenant_id"
STAFF_SESSION_OUTLET_KEY = "staff_outlet_id"
# Session value meaning: show aggregated lists / all outlets (orders, sales).
STAFF_SESSION_OUTLET_ALL = "__all__"
# Active property (site) for lodging lists and front-desk flows.
STAFF_SESSION_SITE_KEY = "staff_site_id"
RETAIL_PIN_IDLE_SECONDS = 8 * 60 * 60


def _subscription_gate(request: HttpRequest, tenant):
    """Block ordinary tenant operations when platform access is not valid."""
    from apps.console.mixins import user_is_platform_operator
    from apps.tenants.subscriptions import tenant_operational_access

    if user_is_platform_operator(request.user):
        return None
    access = tenant_operational_access(tenant)
    request.tenant_operational_access = access
    if access.allowed or request.path == "/staff/pending-approval/":
        return None
    return redirect("staff-pending-approval")


def staff_pin_idle_seconds(request):
    """Effective PIN inactivity limit for the selected, authorized business line.

    Retail tills are assigned to cashiers; hospitality uses short-lived shared
    sessions. Never accept an unverified outlet from the browser to extend an
    idle limit. The same result is reused by middleware and rendered UI.
    """
    cached = getattr(request, "_staff_pin_idle_seconds", None)
    if cached is not None:
        return cached

    from .terminal import PIN_IDLE_SECONDS
    from apps.tenants.models import Outlet, OutletType, TenantSettings
    from .services.membership import (
        staff_accessible_outlets,
        staff_outlet_allowed_for_membership,
    )

    seconds = PIN_IDLE_SECONDS
    membership = getattr(request, "tenant_membership", None)
    if membership is not None:
        selected = request.session.get(STAFF_SESSION_OUTLET_KEY)
        if selected and selected != STAFF_SESSION_OUTLET_ALL:
            try:
                outlet_id = uuid.UUID(str(selected))
            except (TypeError, ValueError, AttributeError):
                outlet_id = None
            if outlet_id and staff_outlet_allowed_for_membership(membership, outlet_id):
                kind = Outlet.objects.filter(
                    pk=outlet_id, site__tenant_id=membership.tenant_id
                ).values_list("outlet_type", flat=True).first()
                if kind in {OutletType.SUPERMARKET, OutletType.RETAIL}:
                    seconds = RETAIL_PIN_IDLE_SECONDS
        else:
            # Retail checkout is an assigned-register workflow. When a mixed
            # workspace has not yet persisted its outlet selection, do not
            # fall back to the two-minute hospitality/shared-terminal timer
            # while the worker is entering the retail checkout route.
            retail_checkout = request.path.startswith("/staff/pos/checkout/")
            if retail_checkout:
                accessible = staff_accessible_outlets(membership)
                if any(
                    outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
                    for outlet in accessible
                ):
                    seconds = RETAIL_PIN_IDLE_SECONDS
            if seconds == PIN_IDLE_SECONDS:
                # A retail-only workspace can use the assigned-register limit
                # even before one outlet is selected. Mixed hospitality stays
                # on the short shared-terminal policy outside retail checkout.
                lines = TenantSettings.objects.filter(
                    tenant_id=membership.tenant_id
                ).values_list("business_lines", flat=True).first() or []
                if lines and set(lines).issubset({"supermarket", "retail", "grocery"}):
                    seconds = RETAIL_PIN_IDLE_SECONDS
    request._staff_pin_idle_seconds = seconds
    return seconds


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
            from .terminal import mark_terminal

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
            if not credential_valid or not isinstance(last, int) or now - last >= staff_pin_idle_seconds(request):
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
        domain_tenant = getattr(request, "domain_tenant", None)
        if domain_tenant is not None and request.user.is_authenticated:
            if path.startswith("/console/platform/"):
                return HttpResponseForbidden("Open platform operations on the platform host.")
            from apps.console.mixins import user_is_platform_operator

            membership = (
                Membership.objects.filter(user=request.user, tenant=domain_tenant, is_active=True)
                .select_related("tenant")
                .first()
            )
            if membership is None and not user_is_platform_operator(request.user):
                return HttpResponseForbidden("Your account has no access to this workspace.")
            request.tenant = domain_tenant
            request.tenant_membership = membership
            blocked = _subscription_gate(request, domain_tenant)
            if blocked is not None:
                return blocked
            return self.get_response(request)
        if path == "/staff/terminal/" and not request.user.is_authenticated:
            from .terminal import terminal_scope

            scope = terminal_scope(request, validate_pairing=False)
            if scope is not None:
                if domain_tenant is not None and str(scope[0]) != str(domain_tenant.pk):
                    return HttpResponseNotFound("Terminal is not available on this workspace domain.")
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
            if path.startswith("/console/"):
                from apps.console.mixins import user_is_platform_operator

                if user_is_platform_operator(request.user):
                    request.tenant = Tenant.objects.filter(pk=tenant_uuid, is_active=True).first()
            return self.get_response(request)

        request.tenant = membership.tenant
        request.tenant_membership = membership
        blocked = _subscription_gate(request, membership.tenant)
        if blocked is not None:
            return blocked

        return self.get_response(request)
