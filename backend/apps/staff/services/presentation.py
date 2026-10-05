"""Profile-specific copy for the shared staff shell."""

from __future__ import annotations

from apps.tenants.business_lines import BUSINESS_LINES, normalize_business_lines
from apps.tenants.models import Outlet, TenantSettings


OUTLET_LINE = {
    "retail": "retail",
    "supermarket": "supermarket",
    "bar": "bar",
    "lounge": "lounge",
    "restaurant": "restaurant",
    "cafeteria": "cafeteria",
    "lodging_front_desk": "lodging",
    "event_space": "events",
    "service": "services",
}

PRESENTATION = {
    "retail": ("Retail workspace", "Sell products, manage stock, and close the register.", ("Sell", "Stock", "Customers", "Reports")),
    "supermarket": ("Store workspace", "Move customers through checkout and keep shelves supplied.", ("Checkout", "Stock", "Suppliers", "Reports")),
    "bar": ("Bar operations", "Manage tabs, prepare drinks, and keep service moving.", ("Orders", "Drink prep", "Serve", "Shift close")),
    "lounge": ("Lounge operations", "Manage guest orders, drink prep, and service.", ("Orders", "Drink prep", "Serve", "Shift close")),
    "restaurant": ("Restaurant operations", "Take orders, coordinate prep, and serve tables.", ("Orders", "Prep", "Tables", "Shift close")),
    "cafeteria": ("Cafeteria operations", "Take orders, coordinate preparation, and keep the line moving.", ("Orders", "Prep", "Serve", "Shift close")),
    "kitchen": ("Kitchen operations", "Track incoming tickets and move prepared items to handoff.", ("Tickets", "Prep", "Handoff", "Stock")),
    "lodging": ("Hotel operations", "Coordinate arrivals, room readiness, guest accounts, and sales.", ("Front desk", "Housekeeping", "Guest accounts", "Reports")),
    "events": ("Events workspace", "Manage bookings, spaces, and event sales.", ("Bookings", "Spaces", "Orders", "Reports")),
    "services": ("Services workspace", "Manage appointments, service packages, and payments.", ("Services", "Schedule", "Payments", "Reports")),
}


def staff_product_presentation(tenant, outlet: Outlet | None = None) -> dict:
    """Choose client-facing terminology from the current outlet or tenant profile."""
    try:
        raw_lines = tenant.settings.business_lines
    except TenantSettings.DoesNotExist:
        raw_lines = []
    lines = normalize_business_lines(raw_lines)
    active_line = OUTLET_LINE.get(getattr(outlet, "outlet_type", ""))
    if active_line in lines:
        key = active_line
    elif len(lines) == 1:
        key = lines[0]
    elif lines:
        key = "combined"
    else:
        key = "legacy"

    if key in PRESENTATION:
        label, tagline, flow = PRESENTATION[key]
    elif key == "combined":
        labels = [BUSINESS_LINES[line].label for line in lines]
        label = " & ".join(labels) + " workspace"
        tagline = "Run daily operations for " + ", ".join(label.lower() for label in labels) + "."
        flow = tuple(labels[:4])
    else:
        label = "Operations workspace"
        tagline = "Manage sales, service, and daily operations in one workspace."
        flow = ("Sales", "Operations", "Stock", "Reports")

    return {
        "workspace_label": label,
        "tagline": tagline,
        "workflow_steps": flow,
        "scope_label": "Register" if key in {"retail", "supermarket"} else "Section",
        "scope_all_label": "All locations" if key in {"retail", "supermarket"} else "All sections",
    }
