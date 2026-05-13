"""Attach API vs staff channel (+ request id) for ``log_audit`` payload enrichment."""

from __future__ import annotations

from typing import Callable

from django.http import HttpRequest, HttpResponse

from .context import reset_audit_request_context, set_audit_request_context


class AuditRequestContextMiddleware:
    """Sets audit context for ``/api/v1/*``, ``/staff/*``, and ``/console/*``."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path
        if path.startswith("/api/v1/"):
            source = "api"
        elif path.startswith("/staff/"):
            source = "staff"
        elif path.startswith("/console/"):
            source = "console"
        else:
            return self.get_response(request)

        rid = getattr(request, "request_id", None)
        token = set_audit_request_context(
            {
                "request_id": str(rid) if rid else None,
                "source": source,
            }
        )
        try:
            return self.get_response(request)
        finally:
            reset_audit_request_context(token)
