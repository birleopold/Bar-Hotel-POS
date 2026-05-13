from __future__ import annotations

import logging
import uuid
from typing import Callable

from django.db import connection, transaction
from django.http import HttpRequest, JsonResponse

from apps.accounts.models import Membership

logger = logging.getLogger(__name__)


def _tenant_error_response(request: HttpRequest, error_body: dict, *, status_code: int) -> JsonResponse:
    payload = dict(error_body)
    rid = getattr(request, "request_id", None)
    if rid:
        payload["request_id"] = str(rid)
    return JsonResponse(payload, status=status_code)


class TenantContextMiddleware:
    """
    Validates optional ``X-Tenant-Id`` against the user's memberships
    and attaches ``request.tenant`` and ``request.tenant_membership``.
    """

    EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
        "/api/v1/health",
        "/api/v1/auth/token",
        "/admin",
        "/static",
    )

    def __init__(self, get_response: Callable[[HttpRequest], object]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request.tenant = None
        request.tenant_membership = None

        path = request.path
        if any(path.startswith(p) for p in self.EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        raw = request.headers.get("X-Tenant-Id")
        if not raw or not request.user.is_authenticated:
            return self.get_response(request)

        try:
            tenant_uuid = uuid.UUID(str(raw))
        except ValueError:
            logger.warning(
                "api.tenant.invalid_header",
                extra={"path": request.path, "request_id": getattr(request, "request_id", None)},
            )
            return _tenant_error_response(
                request,
                {"error": {"code": "invalid_tenant_header", "message": "X-Tenant-Id must be a UUID."}},
                status_code=400,
            )

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
            logger.warning(
                "api.tenant.forbidden",
                extra={
                    "path": request.path,
                    "tenant_id": str(tenant_uuid),
                    "user_id": str(request.user.pk),
                    "request_id": getattr(request, "request_id", None),
                },
            )
            return _tenant_error_response(
                request,
                {
                    "error": {
                        "code": "tenant_forbidden",
                        "message": "You are not a member of this tenant.",
                    }
                },
                status_code=403,
            )

        request.tenant = membership.tenant
        request.tenant_membership = membership

        return self.get_response(request)


class PostgresRequestTenantGucMiddleware:
    """
    When ``POSTGRES_SET_REQUEST_TENANT_GUC`` is True and the DB is PostgreSQL,
    wraps the request in ``transaction.atomic()`` and runs
    ``SET LOCAL app.tenant_id`` so row-level security policies can read it.

    Off by default; enable only with a non-superuser DB role and RLS policies applied.
    """

    def __init__(self, get_response: Callable[[HttpRequest], object]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        from django.conf import settings

        if not getattr(settings, "POSTGRES_SET_REQUEST_TENANT_GUC", False):
            return self.get_response(request)
        tenant = getattr(request, "tenant", None)
        if tenant is None or connection.vendor != "postgresql":
            return self.get_response(request)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL app.tenant_id = %s", [str(tenant.id)])
            return self.get_response(request)
