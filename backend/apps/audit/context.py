"""Per-request audit context (request id + channel) via contextvars."""

from __future__ import annotations

import contextvars
from typing import Any

_audit_request_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "audit_request_context", default=None
)


def set_audit_request_context(data: dict[str, Any] | None):
    return _audit_request_context.set(data)


def reset_audit_request_context(token) -> None:
    _audit_request_context.reset(token)


def get_audit_request_context() -> dict[str, Any]:
    ctx = _audit_request_context.get()
    return dict(ctx) if ctx else {}
