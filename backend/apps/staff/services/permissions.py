from apps.accounts.models import Membership, MembershipRole


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
