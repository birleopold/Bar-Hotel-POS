import uuid
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from apps.access.outlets import membership_outlet_ids
from apps.api.permissions import HasTenantContext, NotReadOnlyRole
from apps.pos.models import PosShift


class RegisterShiftSerializer(serializers.ModelSerializer):
    workstation_id = serializers.UUIDField(read_only=True, allow_null=True)
    workstation_name = serializers.CharField(source="workstation.name", read_only=True, allow_null=True)
    outlet_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = PosShift
        fields = ["id", "outlet_id", "workstation_id", "workstation_name", "status", "opened_at", "closed_at", "opening_cash", "expected_cash", "counted_cash", "cash_attribution"]
        read_only_fields = fields


class RegisterShiftViewSet(viewsets.ReadOnlyModelViewSet):
    """Clients capture the original shift ID before recording offline tenders."""
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = RegisterShiftSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PosShift.objects.none()
        qs = PosShift.objects.filter(tenant=self.request.tenant, outlet_id__in=membership_outlet_ids(self.request.tenant_membership)).select_related("workstation")
        for field in ("outlet", "workstation"):
            value = self.request.query_params.get(field)
            if value:
                try:
                    qs = qs.filter(**{field + "_id": uuid.UUID(value)})
                except ValueError:
                    return PosShift.objects.none()
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs
