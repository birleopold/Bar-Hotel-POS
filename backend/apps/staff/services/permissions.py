from apps.accounts.models import Membership, MembershipRole


def membership_can_modify_lodging(membership: Membership) -> bool:
    return membership.role != MembershipRole.ACCOUNTANT


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
    """Owner / tenant admin only; mirrors API ``CanManageTenantSettings`` + read-only role."""
    if membership.role == MembershipRole.ACCOUNTANT:
        return False
    return membership.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)
