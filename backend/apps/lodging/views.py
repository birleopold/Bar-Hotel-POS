import uuid

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import HasTenantContext, NotReadOnlyRole
from apps.audit.services import log_audit

from .models import Folio, FolioLine, FolioStatus, Reservation, Room, RoomRateWindow, RoomType
from .serializers import (
    FolioCreateSerializer,
    FolioManualLineSerializer,
    FolioPaymentCreateSerializer,
    FolioSerializer,
    FolioStatusSerializer,
    ReservationFolioChargeSerializer,
    ReservationSerializer,
    RoomRateWindowSerializer,
    RoomSerializer,
    RoomTypeSerializer,
)
from .services import cancel_reservation, check_in_reservation, check_out_reservation, close_folio, record_folio_payment


class RoomTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = RoomTypeSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RoomType.objects.none()
        qs = (
            RoomType.objects.filter(tenant=self.request.tenant)
            .select_related("site")
            .order_by("site__name", "name")
        )
        membership = self.request.tenant_membership
        if membership.sites.exists():
            qs = qs.filter(site_id__in=membership.sites.values_list("pk", flat=True))
        return qs


class RoomViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = RoomSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Room.objects.none()
        qs = (
            Room.objects.filter(room_type__tenant=self.request.tenant)
            .select_related("room_type", "room_type__site")
            .order_by("room_type", "name")
        )
        membership = self.request.tenant_membership
        if membership.sites.exists():
            qs = qs.filter(room_type__site_id__in=membership.sites.values_list("pk", flat=True))
        rt = self.request.query_params.get("room_type")
        if rt:
            try:
                qs = qs.filter(room_type_id=uuid.UUID(str(rt)))
            except ValueError:
                return Room.objects.none()
        return qs


class ReservationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = ReservationSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Reservation.objects.none()
        qs = (
            Reservation.objects.filter(tenant=self.request.tenant)
            .select_related("site", "room", "room__room_type")
            .order_by("-check_in", "guest_name")
        )
        membership = self.request.tenant_membership
        if membership.sites.exists():
            qs = qs.filter(site_id__in=membership.sites.values_list("pk", flat=True))
        site = self.request.query_params.get("site")
        if site:
            try:
                qs = qs.filter(site_id=uuid.UUID(str(site)))
            except ValueError:
                return Reservation.objects.none()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return qs

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        reservation = self.get_object()
        check_in_reservation(reservation=reservation, user=request.user)
        reservation.refresh_from_db()
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, pk=None):
        reservation = self.get_object()
        check_out_reservation(reservation=reservation, user=request.user)
        reservation.refresh_from_db()
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        reason = (request.data or {}).get("reason") if hasattr(request, "data") else None
        cancel_reservation(reservation=reservation, user=request.user, reason=str(reason or ""))
        reservation.refresh_from_db()
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="post-folio-charge")
    def post_folio_charge(self, request, pk=None):
        reservation = self.get_object()
        ser = ReservationFolioChargeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        folio = Folio.objects.filter(
            id=vd["folio_id"],
            tenant_id=reservation.tenant_id,
            site_id=reservation.site_id,
            status=FolioStatus.OPEN,
        ).first()
        if folio is None:
            return Response(
                {"error": {"code": "invalid_folio", "message": "Open folio on the same site not found."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        FolioLine.objects.create(
            tenant_id=reservation.tenant_id,
            folio=folio,
            description=vd["description"][:512],
            amount=vd["amount"],
            tax_amount=vd.get("tax_amount") or 0,
        )
        log_audit(
            tenant_id=reservation.tenant_id,
            user_id=request.user.id,
            action="lodging.reservation_folio_charge",
            entity_type="reservation",
            entity_id=str(reservation.id),
            payload={"folio_id": str(folio.id), "amount": str(vd["amount"])},
        )
        folio = (
            Folio.objects.filter(pk=folio.pk)
            .select_related("site", "reservation")
            .prefetch_related("lines", "payments")
            .first()
        )
        return Response(FolioSerializer(folio, context={"request": request}).data)


class RoomRateWindowViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = RoomRateWindowSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RoomRateWindow.objects.none()
        qs = RoomRateWindow.objects.filter(room_type__tenant=self.request.tenant).select_related(
            "room_type", "room_type__site"
        )
        membership = self.request.tenant_membership
        if membership.sites.exists():
            qs = qs.filter(room_type__site_id__in=membership.sites.values_list("pk", flat=True))
        rt = self.request.query_params.get("room_type")
        if rt:
            try:
                qs = qs.filter(room_type_id=uuid.UUID(str(rt)))
            except ValueError:
                return RoomRateWindow.objects.none()
        return qs.order_by("room_type", "valid_from")


class FolioViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Folio.objects.none()
        qs = (
            Folio.objects.filter(tenant=self.request.tenant)
            .select_related("site", "reservation")
            .prefetch_related("lines")
            .order_by("-created_at")
        )
        m = self.request.tenant_membership
        if m.sites.exists():
            qs = qs.filter(site_id__in=m.sites.values_list("pk", flat=True))
        site = self.request.query_params.get("site")
        if site:
            try:
                qs = qs.filter(site_id=uuid.UUID(str(site)))
            except ValueError:
                return Folio.objects.none()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st.strip())
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return FolioCreateSerializer
        if self.action in ("partial_update", "update"):
            return FolioStatusSerializer
        return FolioSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        folio = serializer.save()
        folio = (
            Folio.objects.filter(pk=folio.pk)
            .select_related("site", "reservation")
            .prefetch_related("lines")
            .first()
        )
        return Response(
            FolioSerializer(folio, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        if serializer.validated_data.get("status") == FolioStatus.CLOSED:
            serializer.instance = close_folio(folio=instance, user=self.request.user)
            return
        serializer.save()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        refreshed = (
            Folio.objects.filter(pk=serializer.instance.pk)
            .select_related("site", "reservation")
            .prefetch_related("lines", "payments")
            .get()
        )
        return Response(FolioSerializer(refreshed, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="lines")
    def add_line(self, request, pk=None):
        folio = self.get_object()
        if folio.status != FolioStatus.OPEN:
            return Response(
                {"error": {"code": "folio_closed", "message": "Cannot add lines to a closed folio."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = FolioManualLineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        line = FolioLine.objects.create(
            tenant_id=folio.tenant_id,
            folio=folio,
            description=ser.validated_data["description"][:512],
            amount=ser.validated_data["amount"],
            tax_amount=ser.validated_data.get("tax_amount") or 0,
        )
        log_audit(
            tenant_id=folio.tenant_id,
            user_id=request.user.id,
            action="folio.manual_line",
            entity_type="folio_line",
            entity_id=str(line.id),
            payload={"folio_id": str(folio.id), "amount": str(line.amount)},
        )
        folio = (
            Folio.objects.filter(pk=folio.pk)
            .select_related("site", "reservation")
            .prefetch_related("lines")
            .first()
        )
        return Response(
            FolioSerializer(folio, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="payments")
    def add_payment(self, request, pk=None):
        folio = self.get_object()
        ser = FolioPaymentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payment = record_folio_payment(folio=folio, user=request.user, **ser.validated_data)
        return Response(
            {"id": str(payment.id), "amount": str(payment.amount), "method": payment.method},
            status=status.HTTP_201_CREATED,
        )
