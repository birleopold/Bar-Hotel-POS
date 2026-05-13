"""drf-spectacular postprocessing hooks."""

from __future__ import annotations

from typing import Any

_TENANT_HEADER = {
    "name": "X-Tenant-Id",
    "in": "header",
    "required": False,
    "description": "Active tenant UUID. Required for most authenticated, tenant-scoped routes.",
    "schema": {"type": "string", "format": "uuid"},
}

_SKIP_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/health/",
    "/api/v1/auth/token/",
    "/api/v1/auth/password/reset/",
    "/api/v1/invites/accept/",
    "/api/v1/me/",
)


def postprocess_tenant_header_param(
    result: dict[str, Any],
    generator: Any,
    request: Any,
    public: bool,
) -> dict[str, Any]:
    """Attach X-Tenant-Id to operations except health, JWT, password reset, invite accept, and /me/."""
    paths = result.get("paths")
    if not isinstance(paths, dict):
        return result

    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        if any(path.startswith(p) for p in _SKIP_PATH_PREFIXES):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            params = op.setdefault("parameters", [])
            if not isinstance(params, list):
                continue
            if any(
                isinstance(p, dict) and p.get("name") == "X-Tenant-Id" and p.get("in") == "header"
                for p in params
            ):
                continue
            params.insert(0, dict(_TENANT_HEADER))

    return result
