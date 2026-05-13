from __future__ import annotations

import uuid
from typing import Any

from .context import get_audit_request_context
from .models import AuditEvent


def log_audit(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
    request_id: str | None = None,
    source: str | None = None,
) -> AuditEvent:
    """
    Persist an audit row. ``request_id`` / ``source`` merge into ``payload`` (and fall back to
    middleware-set context for API/staff/console requests). Use ``source`` values:
    ``api``, ``staff``, ``console``, ``system``.
    """
    ctx = get_audit_request_context()
    rid = request_id or ctx.get("request_id")
    src = source or ctx.get("source")
    merged: dict[str, Any] = dict(payload or {})
    if rid:
        merged["request_id"] = str(rid)
    if src:
        merged["source"] = str(src)
    return AuditEvent.objects.create(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=merged,
    )
