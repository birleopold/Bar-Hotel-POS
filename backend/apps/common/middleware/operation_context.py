"""Bind tenant / outlet / user into a logging context for the request (JSON logs)."""

from __future__ import annotations

import contextvars
import logging
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse

# Must stay aligned with apps.staff.middleware (avoid importing staff from common).
_STAFF_OUTLET_SESSION_KEY = "staff_outlet_id"
_STAFF_OUTLET_ALL = "__all__"
_STAFF_SITE_SESSION_KEY = "staff_site_id"

operation_context_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "operation_context", default=None
)


class OperationContextMiddleware:
    """
    After API and staff tenant resolution, attach operation fields for log filters.

    - ``tenant_id`` / ``user_id`` when present on the request
    - ``outlet_id`` from staff/console session outlet selection, or optional ``X-Outlet-Id`` on API
    - ``site_id`` from staff/console branch (site) selection when set in session
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        tenant = getattr(request, "tenant", None)
        tenant_id = str(tenant.id) if tenant is not None else None

        user_id = None
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            user_id = str(user.pk)

        outlet_id: str | None = None
        site_id: str | None = None
        path = request.path
        if path.startswith("/staff/") or path.startswith("/console"):
            raw = request.session.get(_STAFF_OUTLET_SESSION_KEY)
            if raw and str(raw) != _STAFF_OUTLET_ALL:
                outlet_id = str(raw)
            site_raw = request.session.get(_STAFF_SITE_SESSION_KEY)
            if site_raw:
                site_id = str(site_raw)
        elif path.startswith("/api/v1/"):
            raw = (request.headers.get("X-Outlet-Id") or "").strip()
            if raw:
                outlet_id = raw[:64]

        ctx = {
            "tenant_id": tenant_id,
            "outlet_id": outlet_id,
            "site_id": site_id,
            "user_id": user_id,
        }
        token = operation_context_ctx.set(ctx)
        try:
            return self.get_response(request)
        finally:
            operation_context_ctx.reset(token)


class OperationContextLogFilter(logging.Filter):
    """Merges operation context into log records for JsonLogFormatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = operation_context_ctx.get()
        if not ctx:
            return True
        if ctx.get("tenant_id"):
            record.tenant_id = ctx["tenant_id"]
        if ctx.get("outlet_id"):
            record.outlet_id = ctx["outlet_id"]
        if ctx.get("user_id"):
            record.user_id = ctx["user_id"]
        if ctx.get("site_id"):
            record.site_id = ctx["site_id"]
        return True
