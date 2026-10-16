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
    return membership.role in (
        MembershipRole.OWNER,
        MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER,
        MembershipRole.OUTLET_MANAGER,
    )


def membership_can_manage_workspace_settings(membership: Membership) -> bool:
    """Only explicit tenant administrators can change tenant-wide settings/team."""
    return membership.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)


# Phase 20: action-level permissions. The calling view/service must additionally
# enforce enabled modules and its tenant/site/outlet scope.
INVENTORY_CAPABILITY_ROLES = {
    "view": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER, MembershipRole.ACCOUNTANT}),
    "adjust": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER}),
    "transfer": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER}),
    "count": frozenset({MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER, MembershipRole.STOREKEEPER}),
}


def membership_has_inventory_capability(membership: Membership | None, capability: str) -> bool:
    """Fail closed on unknown actions or inactive users; not a scope check."""
    roles = INVENTORY_CAPABILITY_ROLES.get(capability)
    return bool(roles is not None and membership is not None and membership.is_active and membership.role in roles)


# Phase 20: purchasing actions share one role policy. This does not replace
# tenant/module/site/outlet authorization at individual views and services.
PURCHASING_CAPABILITY_ROLES = {
    "view": INVENTORY_CAPABILITY_ROLES["view"],
    "receive": INVENTORY_CAPABILITY_ROLES["adjust"],
    "manage": frozenset({
        MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
    }),
    "supplier_payment": frozenset({
        MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
    }),
}


def membership_has_purchasing_capability(membership: Membership | None, capability: str) -> bool:
    """Fail closed on missing/inactive membership or unsupported action."""
    roles = PURCHASING_CAPABILITY_ROLES.get(capability)
    return bool(roles is not None and membership is not None and membership.is_active and membership.role in roles)
