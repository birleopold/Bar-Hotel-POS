from __future__ import annotations

from apps.accounts.models import MembershipRole
from apps.staff.services.permissions import (
    INVENTORY_CAPABILITY_ROLES,
    PURCHASING_CAPABILITY_ROLES,
    SENSITIVE_APPROVAL_ACTIONS,
    SENSITIVE_APPROVAL_ROLES,
)


ROLE_SUMMARIES = {
    MembershipRole.OWNER: "Full tenant control, including workspace settings and all branches.",
    MembershipRole.TENANT_ADMIN: "Tenant-wide administration without platform-owner powers.",
    MembershipRole.SITE_MANAGER: "Operational manager for assigned branches.",
    MembershipRole.OUTLET_MANAGER: "Operational manager for assigned sales areas.",
    MembershipRole.SERVER: "Checkout/floor worker for assigned compatible sales areas.",
    MembershipRole.BARTENDER: "Bar service worker for assigned bar/lounge areas.",
    MembershipRole.KITCHEN: "Kitchen/preparation worker for assigned hospitality areas.",
    MembershipRole.STOREKEEPER: "Stock and receiving worker for assigned compatible areas.",
    MembershipRole.FRONT_DESK: "Front-desk worker for assigned lodging/event/service areas.",
    MembershipRole.ACCOUNTANT: "Read-oriented financial and inventory visibility.",
    MembershipRole.CLEANER: "Housekeeping worker for assigned lodging branches.",
}


def _label(role: str) -> str:
    return dict(MembershipRole.choices).get(role, role.replace("_", " ").title())


def role_access_preview(role: str) -> dict:
    """Human-readable preview derived from the same built-in role policies.

    This does not grant access. Views/services continue to enforce role,
    enabled-module and tenant/site/outlet scope independently.
    """
    groups: list[dict] = []

    sales = []
    if role in {
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
        MembershipRole.SERVER,
        MembershipRole.BARTENDER,
    }:
        sales.append("Use checkout/orders in assigned compatible areas")
    if role in {
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
    }:
        sales.append("Review manager-only transaction actions")
    if role == MembershipRole.KITCHEN:
        sales.append("Use kitchen/preparation workflow")
    if sales:
        groups.append({"label": "Sales & service", "items": sales})

    inventory = [
        label
        for capability, label in (
            ("view", "View stock"),
            ("adjust", "Post stock adjustments"),
            ("transfer", "Transfer stock"),
            ("request_transfer", "Request stock transfers"),
            ("approve_transfer", "Approve stock transfers"),
            ("count", "Perform stock counts"),
            ("approve_count", "Approve stock counts"),
        )
        if role in INVENTORY_CAPABILITY_ROLES.get(capability, ())
    ]
    if inventory:
        groups.append({"label": "Inventory", "items": inventory})

    purchasing = [
        label
        for capability, label in (
            ("view", "View purchasing"),
            ("request", "Prepare purchase requests"),
            ("receive", "Receive deliveries"),
            ("manage", "Manage purchase orders"),
            ("approve", "Approve purchase requests/orders"),
            ("supplier_payment", "Record/approve supplier payment actions"),
        )
        if role in PURCHASING_CAPABILITY_ROLES.get(capability, ())
    ]
    if purchasing:
        groups.append({"label": "Purchasing", "items": purchasing})

    if role in SENSITIVE_APPROVAL_ROLES:
        actions = ", ".join(sorted(action.replace("_", " ") for action in SENSITIVE_APPROVAL_ACTIONS))
        groups.append({
            "label": "Manager approvals",
            "items": [f"May approve authorized sensitive actions: {actions}"],
        })

    hospitality = []
    if role in {
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
        MembershipRole.FRONT_DESK,
    }:
        hospitality.extend(["Manage reservations", "Manage guest folios"])
    if role in {
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
        MembershipRole.FRONT_DESK,
        MembershipRole.CLEANER,
    }:
        hospitality.append("Access housekeeping workflow")
    if hospitality:
        groups.append({"label": "Hospitality", "items": hospitality})

    admin = []
    if role in {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}:
        admin.extend(["Manage workspace settings", "Manage workers and invites"])
    if role in {
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
    }:
        admin.append("Use management exception/review workspace")
    if role == MembershipRole.ACCOUNTANT:
        admin.append("Read financial and operational reporting surfaces allowed by enabled modules")
    if admin:
        groups.append({"label": "Administration & reporting", "items": admin})

    return {
        "role": role,
        "role_label": _label(role),
        "summary": ROLE_SUMMARIES.get(role, "Built-in role"),
        "groups": groups,
        "scope_note": (
            "Actual access is further restricted by enabled business modules, assigned branches, "
            "assigned outlets and outlet-type compatibility."
        ),
    }
