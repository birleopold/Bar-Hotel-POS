import uuid

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.models import Membership


class TenantJWTAuthentication(JWTAuthentication):
    """Authenticate JWTs and resolve the tenant header after DRF knows the user."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        raw = (request.headers.get("X-Tenant-Id") or "").strip()
        if not raw:
            return user, token
        try:
            tenant_id = uuid.UUID(raw)
        except ValueError as exc:
            raise AuthenticationFailed("X-Tenant-Id must be a UUID.", code="invalid_tenant_header") from exc
        membership = (
            Membership.objects.filter(user=user, tenant_id=tenant_id, is_active=True)
            .select_related("tenant")
            .first()
        )
        if membership is None:
            raise AuthenticationFailed("You are not a member of this tenant.", code="tenant_forbidden")
        request.tenant = membership.tenant
        request.tenant_membership = membership
        return user, token


class TenantJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.authentication.TenantJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
