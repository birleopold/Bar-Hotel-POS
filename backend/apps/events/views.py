import uuid

from rest_framework import viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.accounts.models import MembershipRole
from apps.api.permissions import HasTenantContext, NotReadOnlyRole
from apps.staff.services.modules import get_tenant_staff_modules
from apps.tenants.business_lines import normalize_business_lines

from .models import EventBooking, EventSpace
from .serializers import EventBookingSerializer, EventSpaceSerializer


class EventSpaceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = EventSpaceSerializer

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsAuthenticated(), HasTenantContext(), NotReadOnlyRole(), EventsModuleEnabled(), CanManageEvents()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EventSpace.objects.none()
        qs = EventSpace.objects.filter(tenant=self.request.tenant).select_related("site")
        if not _events_enabled(self.request.tenant):
            return EventSpace.objects.none()
        membership = self.request.tenant_membership
        if membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or membership.sites.exists():
            qs = qs.filter(site_id__in=membership.sites.values_list("pk", flat=True))
        if membership.role == MembershipRole.CLEANER:
            qs = qs.none()
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

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update"}:
            return [IsAuthenticated(), HasTenantContext(), NotReadOnlyRole(), EventsModuleEnabled(), CanManageEvents()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EventBooking.objects.none()
        qs = EventBooking.objects.filter(tenant=self.request.tenant).select_related("space", "space__site")
        if not _events_enabled(self.request.tenant):
            return EventBooking.objects.none()
        membership = self.request.tenant_membership
        if membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or membership.sites.exists():
            qs = qs.filter(space__site_id__in=membership.sites.values_list("pk", flat=True))
        if membership.role == MembershipRole.CLEANER:
            qs = qs.none()
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


def _events_enabled(tenant) -> bool:
    try:
        return "events" in normalize_business_lines(tenant.settings.business_lines) and "events" in get_tenant_staff_modules(tenant)
    except Exception:
        return False


class EventsModuleEnabled(BasePermission):
    message = "Events are not enabled for this workspace."

    def has_permission(self, request, view):
        return _events_enabled(request.tenant)


class CanManageEvents(BasePermission):
    message = "Your role cannot modify event records."

    def has_permission(self, request, view):
        return request.tenant_membership.role in (
            MembershipRole.OWNER,
            MembershipRole.TENANT_ADMIN,
            MembershipRole.SITE_MANAGER,
            MembershipRole.OUTLET_MANAGER,
        )
