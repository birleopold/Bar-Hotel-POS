from __future__ import annotations

from apps.tenants.business_lines import normalize_business_lines
from apps.tenants.models import Tenant, TenantSettings


def console_business_line_flags(tenant: Tenant, *, legacy_defaults: bool = True) -> dict[str, bool]:
    try:
        settings_obj = tenant.settings
    except TenantSettings.DoesNotExist:
        lines: list[str] = []
    else:
        lines = normalize_business_lines(getattr(settings_obj, "business_lines", None))

    bl = set(lines)
    legacy_unconfigured = not bl and legacy_defaults
    has_fnb = bool(bl & {"bar", "lounge", "restaurant", "cafeteria", "kitchen"})
    has_retail = bool(bl & {"retail", "supermarket"})
    has_inventory_work = has_fnb or has_retail
    has_lodging = "lodging" in bl
    has_events = "events" in bl
    has_services = "services" in bl

    return {
        "console_has_fnb": has_fnb or legacy_unconfigured,
        "console_has_retail": has_retail or legacy_unconfigured,
        "console_has_inventory_work": has_inventory_work or legacy_unconfigured,
        "console_has_lodging": has_lodging or legacy_unconfigured,
        "console_has_events": has_events or legacy_unconfigured,
        "console_has_services": has_services or legacy_unconfigured,
        "console_business_lines": lines,
    }
