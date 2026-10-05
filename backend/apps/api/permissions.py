from rest_framework import permissions

from apps.accounts.models import MembershipRole


class HasTenantContext(permissions.BasePermission):
    """Requires authenticated user and valid ``X-Tenant-Id`` (middleware sets ``request.tenant``)."""

    message = "Send header X-Tenant-Id with a tenant you belong to."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        tenant = getattr(request, "tenant", None)
        membership = getattr(request, "tenant_membership", None)
        return tenant is not None and membership is not None


class HasTenantModule(permissions.BasePermission):
    """Gate tenant API families with the same profile/plan module resolution as staff UI."""

    message = "This feature is not enabled for this workspace."

    def has_permission(self, request, view) -> bool:
        module = getattr(view, "required_staff_module", None)
        if not module:
            return True
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return False
        from apps.staff.services.modules import get_tenant_staff_modules

        return module in get_tenant_staff_modules(tenant)


class CanUseKds(permissions.BasePermission):
    message = "Kitchen prep is not enabled or your role cannot access the prep queue."

    def has_permission(self, request, view) -> bool:
        from apps.accounts.models import MembershipRole
        from apps.staff.services.modules import get_tenant_staff_modules

        membership = getattr(request, "tenant_membership", None)
        tenant = getattr(request, "tenant", None)
        allowed_roles = {
            MembershipRole.OWNER,
            MembershipRole.TENANT_ADMIN,
            MembershipRole.SITE_MANAGER,
            MembershipRole.OUTLET_MANAGER,
            MembershipRole.KITCHEN,
            MembershipRole.BARTENDER,
        }
        return bool(
            membership
            and tenant
            and membership.role in allowed_roles
            and "kitchen" in get_tenant_staff_modules(tenant)
        )


class CanManageTenantSettings(permissions.BasePermission):
    """PATCH tenant branding/settings: owner or tenant_admin only."""

    message = "Only owner or tenant admin can update tenant settings."

    def has_permission(self, request, view) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        m = getattr(request, "tenant_membership", None)
        if m is None:
            return False
        return m.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)


class NotReadOnlyRole(permissions.BasePermission):
    """Blocks unsafe methods for tenant members with accountant (read-only) role."""

    message = "Your role is read-only for this tenant."

    def has_permission(self, request, view) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        membership = getattr(request, "tenant_membership", None)
        if membership is None:
            return False
        return membership.role != MembershipRole.ACCOUNTANT


class CanApproveRefunds(permissions.BasePermission):
    message = "Only owners and managers can approve refunds."

    def has_permission(self, request, view) -> bool:
        membership = getattr(request, "tenant_membership", None)
        return membership is not None and membership.role in (
            MembershipRole.OWNER,
            MembershipRole.TENANT_ADMIN,
            MembershipRole.SITE_MANAGER,
            MembershipRole.OUTLET_MANAGER,
        )


class CanManageIntegrations(permissions.BasePermission):
    message = "Only owners and tenant admins can access integration configuration."

    def has_permission(self, request, view) -> bool:
        membership = getattr(request, "tenant_membership", None)
        return membership is not None and membership.role in (
            MembershipRole.OWNER,
            MembershipRole.TENANT_ADMIN,
        )
