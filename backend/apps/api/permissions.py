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
