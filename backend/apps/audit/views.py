from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.api.permissions import HasTenantContext

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditEvent.objects.none()
        return AuditEvent.objects.filter(tenant=self.request.tenant).select_related("user")
