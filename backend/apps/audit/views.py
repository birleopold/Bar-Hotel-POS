from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.api.permissions import HasTenantContext
from apps.staff.services.audit_reader import visible_audit_events

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditEvent.objects.none()
        queryset, _filters = visible_audit_events(
            tenant=self.request.tenant,
            membership=self.request.tenant_membership,
            params=self.request.query_params,
        )
        return queryset
