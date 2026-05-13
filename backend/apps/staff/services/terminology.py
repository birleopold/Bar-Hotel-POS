from __future__ import annotations

from apps.tenants.business_lines import normalize_business_lines
from apps.tenants.models import Outlet, Tenant, TenantSettings


def staff_action_overrides_for_tenant(
    tenant: Tenant,
    *,
    outlet: Outlet | None = None,
) -> dict[str, tuple[str, str]]:
    """
    Return dashboard action label/hint overrides based on tenant business lines.

    Output mapping: capability_key -> (label, hint)
    """
    try:
        settings_obj = tenant.settings
    except TenantSettings.DoesNotExist:
        return {}

    lines = normalize_business_lines(getattr(settings_obj, "business_lines", None))
    if not lines:
        return {}

    # Choose a primary line for terminology.
    # Prefer the active outlet type when available.
    outlet_type = (getattr(outlet, "outlet_type", "") or "").strip()
    if outlet_type == "supermarket":
        primary = "supermarket"
    elif outlet_type == "retail":
        primary = "retail"
    elif outlet_type in {"bar", "lounge", "restaurant", "cafeteria", "lodging_front_desk", "event_space"}:
        primary = {
            "bar": "bar",
            "lounge": "lounge",
            "restaurant": "restaurant",
            "cafeteria": "cafeteria",
            "lodging_front_desk": "lodging",
            "event_space": "events",
        }.get(outlet_type, lines[0])
    else:
        primary = lines[0]

    # Baseline: simpler words everywhere.
    overrides: dict[str, tuple[str, str]] = {
        "orders": ("Orders", "Create and settle orders"),
        "kitchen": ("Prep queue", "Prep and serve"),
        "menu": ("Items", "Sellable items"),
        "promotions": ("Offers", "Promos and discounts"),
        "inventory": ("Stock", "On-hand stock"),
        "purchasing": ("Suppliers", "Purchase orders"),
        "workspace": ("Team & settings", "Users, roles, setup"),
        "events": ("Bookings", "Events & spaces"),
        "lodging": ("Front desk", "Guests & rooms"),
        "tables": ("Tables", "Floor"),
        "sales": ("Reports", "Sales summary"),
    }

    # Per-line refinements.
    if primary in {"restaurant", "bar", "lounge", "cafeteria"}:
        overrides.update(
            {
                "orders": ("Orders", "Open and pay orders"),
                "menu": ("Items", "Food and drinks"),
                "tables": ("Tables", "Dining tables"),
            }
        )

    if primary in {"retail", "supermarket"}:
        overrides.update(
            {
                "orders": ("Sales", "Checkout and payments"),
                "menu": ("Products", "Items for sale"),
            }
        )

    if primary == "lodging":
        overrides.update(
            {
                "lodging": ("Front desk", "Check-in, check-out"),
                "orders": ("Charges", "Post charges"),
                "menu": ("Services", "Sell services"),
            }
        )

    if primary == "events":
        overrides.update(
            {
                "events": ("Bookings", "Reservations for spaces"),
                "orders": ("Payments", "Collect deposits/payments"),
            }
        )

    return overrides
