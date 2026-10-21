"""Tenant-specific staff role options, shared by browser and API workflows."""
from apps.accounts.models import MembershipRole
from apps.tenants.business_lines import normalize_business_lines

COMMON = {
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
    MembershipRole.ACCOUNTANT,
}
LINE_ROLES = {
    "bar": {MembershipRole.BARTENDER, MembershipRole.SERVER, MembershipRole.KITCHEN, MembershipRole.STOREKEEPER},
    "lounge": {MembershipRole.BARTENDER, MembershipRole.SERVER, MembershipRole.KITCHEN, MembershipRole.STOREKEEPER},
    "restaurant": {MembershipRole.SERVER, MembershipRole.KITCHEN, MembershipRole.STOREKEEPER},
    "cafeteria": {MembershipRole.SERVER, MembershipRole.KITCHEN, MembershipRole.STOREKEEPER},
    "kitchen": {MembershipRole.KITCHEN, MembershipRole.STOREKEEPER},
    "lodging": {MembershipRole.FRONT_DESK, MembershipRole.CLEANER, MembershipRole.STOREKEEPER},
    "retail": {MembershipRole.SERVER, MembershipRole.STOREKEEPER},
    "supermarket": {MembershipRole.SERVER, MembershipRole.STOREKEEPER},
    "events": {MembershipRole.FRONT_DESK, MembershipRole.SERVER},
    "services": {MembershipRole.FRONT_DESK, MembershipRole.SERVER},
}


def permitted_roles(tenant):
    """Use union for mixed businesses, fail closed until business lines set."""
    try:
        lines = normalize_business_lines(tenant.settings.business_lines)
    except (AttributeError, ValueError, TypeError):
        lines = []
    roles = set(COMMON)
    for line in lines:
        roles.update(LINE_ROLES.get(line, ()))
    return roles


def role_choices_for_tenant(tenant, *, include_admin=True):
    allowed = permitted_roles(tenant)
    if not include_admin:
        allowed -= {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}
    return [(value, label) for value, label in MembershipRole.choices if value in allowed]
