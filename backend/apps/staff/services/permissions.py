from apps.accounts.models import Membership, MembershipRole


def membership_can_modify_inventory(membership: Membership) -> bool:
    return membership_has_inventory_capability(membership, "adjust")


def membership_can_modify_lodging(membership: Membership) -> bool:
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
    )


def membership_can_manage_room_inventory(membership: Membership) -> bool:
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
    )


def membership_can_update_housekeeping(membership: Membership) -> bool:
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
        MembershipRole.CLEANER,
    )


def membership_can_manage_housekeeping_workflows(membership: Membership) -> bool:
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
    )


def membership_can_manage_folios(membership: Membership) -> bool:
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
        MembershipRole.FRONT_DESK,
    )


def membership_can_view_folios(membership: Membership) -> bool:
    return membership_can_manage_folios(membership)


def membership_can_manage_reservations(membership: Membership) -> bool:
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
        MembershipRole.FRONT_DESK,
    )


def membership_can_access_housekeeping(membership: Membership) -> bool:
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
        MembershipRole.FRONT_DESK,
        MembershipRole.CLEANER,
    )


def membership_can_manage_kitchen(membership: Membership) -> bool:
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
        MembershipRole.KITCHEN,
        MembershipRole.BARTENDER,
    )


def membership_can_acknowledge_ready_handoff(
    membership: Membership, *, is_assigned_server: bool
) -> bool:
    if membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
    ):
        return True
    if membership.role in (
        MembershipRole.SERVER,
        MembershipRole.BARTENDER,
        MembershipRole.FRONT_DESK,
    ):
        return is_assigned_server
    return False


def membership_can_approve_refunds(membership: Membership) -> bool:
    return membership_can_approve_sensitive_action(membership, "refund")


def membership_can_manage_workspace_settings(membership: Membership) -> bool:
    """Only explicit tenant administrators can change tenant-wide settings/team."""
    return membership.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)


# Phase 20: action-level permissions. The calling view/service must additionally
# enforce enabled modules and its tenant/site/outlet scope.
INVENTORY_CAPABILITY_ROLES = {
    "view": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER, MembershipRole.ACCOUNTANT}),
    "adjust": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER}),
    "transfer": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER}),
    "request_transfer": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER}),
    "approve_transfer": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER}),
    "count": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER}),
    "approve_count": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER}),
}


def membership_has_inventory_capability(membership: Membership | None, capability: str) -> bool:
    """Fail closed on unknown actions or inactive users; not a scope check."""
    roles = INVENTORY_CAPABILITY_ROLES.get(capability)
    return bool(roles is not None and membership is not None and membership.is_active and membership.role in roles)


# Phase 20: purchasing actions share one role policy. This does not replace
# tenant/module/site/outlet authorization at individual views and services.
PURCHASING_MANAGER_ROLES = frozenset({
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
})

PURCHASING_CAPABILITY_ROLES = {
    "view": INVENTORY_CAPABILITY_ROLES["view"],
    "request": INVENTORY_CAPABILITY_ROLES["adjust"],
    "receive": INVENTORY_CAPABILITY_ROLES["adjust"],
    "manage": PURCHASING_MANAGER_ROLES,
    "approve": PURCHASING_MANAGER_ROLES,
    "supplier_payment": PURCHASING_MANAGER_ROLES,
}


def membership_has_purchasing_capability(membership: Membership | None, capability: str) -> bool:
    """Fail closed on missing/inactive membership or unsupported action."""
    roles = PURCHASING_CAPABILITY_ROLES.get(capability)
    return bool(roles is not None and membership is not None and membership.is_active and membership.role in roles)


# Phase 21 foundation: explicit manager authority for sensitive financial actions.
# Authority to perform an action is NOT an issued approval: request/approver PIN,
# immutable exact-action intent, expiry, and single use need separate enforcement.
SENSITIVE_APPROVAL_ROLES = frozenset({
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
})
SENSITIVE_APPROVAL_ACTIONS = frozenset({
    "refund", "retail_line_refund", "discount", "void",
    "reopen", "stock_write_off", "price_override", "withdrawal",
})


def membership_can_approve_sensitive_action(membership: Membership | None, action: str) -> bool:
    """Role eligibility only; fail closed for invalid, inactive or unknown actors."""
    return bool(
        action in SENSITIVE_APPROVAL_ACTIONS
        and membership is not None and membership.is_active
        and membership.role in SENSITIVE_APPROVAL_ROLES
    )


def membership_can_confirm_retail_pickup(membership: Membership | None) -> bool:
    """Retail handover role check; callers also validate outlet and tenant scope."""
    return bool(
        membership is not None and membership.is_active
        and membership.role in {
            MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
            MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
        }
    )
