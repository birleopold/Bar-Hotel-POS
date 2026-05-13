"""Attach a stable request id for tracing (logs + response header)."""

from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
RESPONSE_HEADER = "X-Request-ID"

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raw = (request.META.get(REQUEST_ID_HEADER) or "").strip()
        if raw and len(raw) <= 128:
            rid = raw[:128]
        else:
            rid = str(uuid.uuid4())
        request.request_id = rid  # type: ignore[attr-defined]

        token = request_id_ctx.set(rid)
        try:
            response = self.get_response(request)
        finally:
            request_id_ctx.reset(token)

        if isinstance(response, HttpResponse):
            response[RESPONSE_HEADER] = rid
        return response


class RequestIdLogFilter(logging.Filter):
    """Adds request_id from context to log records (for JsonLogFormatter)."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = request_id_ctx.get()
        if rid:
            record.request_id = rid
        return True
