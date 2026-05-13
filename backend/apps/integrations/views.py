from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.api.permissions import CanManageTenantSettings, HasTenantContext, NotReadOnlyRole

from .models import IntegrationLink
from .serializers import IntegrationLinkSerializer


class IntegrationLinkViewSet(viewsets.ModelViewSet):
    """Tenant integration registry (owner / tenant_admin for writes)."""

    permission_classes = [
        IsAuthenticated,
        HasTenantContext,
        CanManageTenantSettings,
        NotReadOnlyRole,
    ]
    serializer_class = IntegrationLinkSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return IntegrationLink.objects.none()
        return IntegrationLink.objects.filter(tenant=self.request.tenant).order_by("provider_key")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)
