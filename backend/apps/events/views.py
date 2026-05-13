import uuid

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.api.permissions import HasTenantContext, NotReadOnlyRole

from .models import EventBooking, EventSpace
from .serializers import EventBookingSerializer, EventSpaceSerializer


class EventSpaceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = EventSpaceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EventSpace.objects.none()
        qs = EventSpace.objects.filter(tenant=self.request.tenant).select_related("site")
        membership = self.request.tenant_membership
        if membership.sites.exists():
            qs = qs.filter(site_id__in=membership.sites.values_list("pk", flat=True))
        site = self.request.query_params.get("site")
        if site:
            try:
                qs = qs.filter(site_id=uuid.UUID(str(site)))
            except ValueError:
                return EventSpace.objects.none()
        return qs.order_by("site__name", "name")


class EventBookingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = EventBookingSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EventBooking.objects.none()
        qs = EventBooking.objects.filter(tenant=self.request.tenant).select_related("space", "space__site")
        membership = self.request.tenant_membership
        if membership.sites.exists():
            qs = qs.filter(space__site_id__in=membership.sites.values_list("pk", flat=True))
        space = self.request.query_params.get("space")
        if space:
            try:
                qs = qs.filter(space_id=uuid.UUID(str(space)))
            except ValueError:
                return EventBooking.objects.none()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st.strip())
        return qs.order_by("start_at")
