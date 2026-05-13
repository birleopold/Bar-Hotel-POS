"""Unified API error JSON: ``error`` object + ``request_id`` (see docs/AUDIT_RECOMMENDATIONS.md)."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def _http_status_to_code(http_status: int) -> str:
    mapping: dict[int, str] = {
        status.HTTP_400_BAD_REQUEST: "bad_request",
        status.HTTP_401_UNAUTHORIZED: "not_authenticated",
        status.HTTP_403_FORBIDDEN: "permission_denied",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_406_NOT_ACCEPTABLE: "not_acceptable",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
        status.HTTP_429_TOO_MANY_REQUESTS: "throttled",
    }
    return mapping.get(http_status, "error")


def api_exception_handler(exc: BaseException, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    request = context.get("request")
    rid = getattr(request, "request_id", None) if request else None
    rid_s = str(rid) if rid else None

    if response is None:
        if not settings.DEBUG and request and getattr(request, "path", "").startswith("/api/v1/"):
            logger.exception("Unhandled exception in API request", exc_info=exc)
            return Response(
                {
                    "error": {
                        "code": "server_error",
                        "message": "An unexpected error occurred.",
                        "details": None,
                    },
                    **({"request_id": rid_s} if rid_s else {}),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return None

    data = response.data
    out: dict[str, Any]

    if isinstance(data, dict) and "error" in data and isinstance(data["error"], dict):
        err = dict(data["error"])
        if "details" not in err:
            err["details"] = None
        out = {"error": err}
    elif isinstance(data, dict) and "detail" in data and len(data) == 1:
        out = {
            "error": {
                "code": _http_status_to_code(response.status_code),
                "message": str(data["detail"]),
                "details": None,
            }
        }
    elif isinstance(data, dict):
        msg = (
            "Invalid input."
            if response.status_code == status.HTTP_400_BAD_REQUEST
            else "Request failed."
        )
        code = (
            "validation_error"
            if response.status_code == status.HTTP_400_BAD_REQUEST
            else _http_status_to_code(response.status_code)
        )
        out = {"error": {"code": code, "message": msg, "details": data}}
    else:
        out = {
            "error": {
                "code": "error",
                "message": str(data),
                "details": None,
            }
        }

    if rid_s:
        out["request_id"] = rid_s
    response.data = out
    return response
