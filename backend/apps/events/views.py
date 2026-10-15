import uuid

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.accounts.models import MembershipRole
from apps.api.permissions import HasTenantContext, NotReadOnlyRole
from apps.staff.services.modules import get_tenant_staff_modules
from apps.tenants.business_lines import normalize_business_lines

from .models import EventBooking, EventSpace, EventQuote
from .serializers import (EventBookingSerializer, EventSpaceSerializer,
    CreateEventQuoteSerializer, ChangeEventQuoteSerializer, CreateEventPaymentSerializer,
    EventQuoteSerializer, EventPaymentSerializer)
from .services_journey import create_event_quote, change_event_quote_status, record_event_payment


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
        if self.action in {"create", "update", "partial_update",
                           "create_quote", "change_quote", "record_payment"}:
            return [IsAuthenticated(), HasTenantContext(), NotReadOnlyRole(),
                    EventsModuleEnabled(), CanManageEvents()]
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

    @action(detail=True, methods=["post"], url_path="quotes")
    def create_quote(self, request, pk=None):
        booking = self.get_object()
        form = CreateEventQuoteSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        quote = create_event_quote(
            booking=booking, membership=request.tenant_membership,
            user=request.user, **form.validated_data,
        )
        return Response(EventQuoteSerializer(quote).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="quote-status")
    def change_quote(self, request, pk=None):
        booking = self.get_object()
        form = ChangeEventQuoteSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        quote = EventQuote.objects.filter(
            tenant=request.tenant, booking=booking,
            id=form.validated_data["quote_id"],
        ).first()
        if quote is None:
            raise ValidationError({"quote_id": "Quotation not found for this event."})
        updated = change_event_quote_status(
            quote=quote, membership=request.tenant_membership, user=request.user,
            action=form.validated_data["action"],
        )
        return Response(EventQuoteSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="payments")
    def record_payment(self, request, pk=None):
        booking = self.get_object()
        form = CreateEventPaymentSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        payment, repeated = record_event_payment(
            booking=booking, membership=request.tenant_membership,
            user=request.user, **form.validated_data,
        )
        return Response(
            EventPaymentSerializer(payment).data,
            status=status.HTTP_200_OK if repeated else status.HTTP_201_CREATED,
        )


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
