import uuid
from django.db.models import Q

from apps.access.outlets import membership_outlet_ids, outlet_belongs_to_membership
from apps.catalog.models import MenuItem
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from apps.api.permissions import HasTenantContext, HasTenantModule, NotReadOnlyRole

from .models import StockBalance, StockShelfLocation, StockCountSession, StockCountStatus, StockMovement, StockTransferReceipt
from .serializers import (
    StockBalanceSerializer,
    ShelfLocationReadSerializer,
    ShelfLocationWriteSerializer,
    StockCountCompleteSerializer,
    StockCountSessionCreateSerializer,
    StockCountSessionSerializer,
    StockMovementSerializer,
    StockMovementWriteSerializer,
    StockTransferSerializer,
)
from .services import (
    complete_stock_count_session, submit_stock_count_for_review,
    approve_stock_count_session, return_stock_count_for_recount,
    verify_stock_transfer_receipt, resolve_stock_transfer_discrepancy,
)
from apps.staff.services.permissions import membership_has_inventory_capability


class CanViewInventory(BasePermission):
    message = "Your role cannot view inventory records."

    def has_permission(self, request, view):
        return membership_has_inventory_capability(
            getattr(request, "tenant_membership", None),
            "view",
        )


class StockShelfLocationViewSet(viewsets.GenericViewSet):
    """Fast searchable shelf addresses, updated without changing inventory quantities."""
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, CanViewInventory]
    required_staff_module = "inventory"
    serializer_class = ShelfLocationReadSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockShelfLocation.objects.none()
        return StockShelfLocation.objects.filter(
            tenant=self.request.tenant,
            outlet_id__in=membership_outlet_ids(self.request.tenant_membership),
        ).select_related("outlet", "menu_item").order_by("outlet__name", "menu_item__name")

    def list(self, request):
        qs = self.get_queryset()
        raw = request.query_params.get("outlet")
        if raw:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(raw)))
            except (ValueError, TypeError):
                qs = qs.none()
        term = (request.query_params.get("q") or "").strip()[:80]
        if term:
            qs = qs.filter(
                Q(menu_item__name__icontains=term) | Q(menu_item__sku__icontains=term)
                | Q(menu_item__barcode__icontains=term) | Q(aisle__icontains=term)
                | Q(shelf__icontains=term) | Q(bin_code__icontains=term)
            )
        return Response(ShelfLocationReadSerializer(qs[:100], many=True).data)

    def create(self, request):
        from .services_shelves import set_stock_shelf_location
        serializer = ShelfLocationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        location, replay = set_stock_shelf_location(
            tenant_id=request.tenant.pk, membership=request.tenant_membership,
            user=request.user, **serializer.validated_data,
        )
        return Response(ShelfLocationReadSerializer(location).data,
                        status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED)


class StockBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, CanViewInventory]
    required_staff_module = "inventory"
    serializer_class = StockBalanceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockBalance.objects.none()
        qs = (
            StockBalance.objects.filter(
                tenant=self.request.tenant,
                outlet_id__in=membership_outlet_ids(self.request.tenant_membership),
            )
            .select_related("outlet", "menu_item")
            .order_by("outlet", "menu_item__name")
        )
        outlet = self.request.query_params.get("outlet")
        if outlet:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet)))
            except ValueError:
                return StockBalance.objects.none()
        low = self.request.query_params.get("low_stock")
        if low and low.lower() in ("1", "true", "yes"):
            from django.db.models import F

            qs = qs.filter(
                menu_item__track_inventory=True,
                menu_item__reorder_level__isnull=False,
            ).filter(quantity__lte=F("menu_item__reorder_level"))
        return qs


class StockMovementViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole, CanViewInventory]
    required_staff_module = "inventory"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockMovement.objects.none()
        qs = StockMovement.objects.filter(
            tenant=self.request.tenant,
            outlet_id__in=membership_outlet_ids(self.request.tenant_membership),
        ).select_related(
            "outlet", "menu_item", "order", "purchase_order", "created_by"
        )
        outlet = self.request.query_params.get("outlet")
        if outlet:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet)))
            except ValueError:
                return StockMovement.objects.none()
        tb = self.request.query_params.get("transfer_batch")
        if tb:
            try:
                qs = qs.filter(transfer_batch=uuid.UUID(str(tb)))
            except ValueError:
                return StockMovement.objects.none()
        po = self.request.query_params.get("purchase_order")
        if po:
            try:
                qs = qs.filter(purchase_order_id=uuid.UUID(str(po)))
            except ValueError:
                return StockMovement.objects.none()
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return StockMovementWriteSerializer
        return StockMovementSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement = serializer.save()
        return Response(
            StockMovementSerializer(movement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class StockTransferViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole, CanViewInventory]
    required_staff_module = "inventory"
    serializer_class = StockTransferSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockMovement.objects.none()
        return StockMovement.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch, mov_out, mov_in = serializer.save()
        return Response(
            {
                "transfer_batch": str(batch),
                "from_movement_id": str(mov_out.id),
                "to_movement_id": str(mov_in.id) if mov_in is not None else None,
                "status": "posted" if mov_in is not None else "in_transit",
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="receipts")
    def receipts(self, request):
        ids = membership_outlet_ids(request.tenant_membership)
        transfers = StockTransferReceipt.objects.filter(
            tenant=request.tenant,
        ).filter(Q(from_outlet_id__in=ids) | Q(to_outlet_id__in=ids)).order_by("-created_at")[:100]
        return Response([{
            "id": str(r.id), "reference": str(r.transfer_batch),
            "from_outlet": str(r.from_outlet_id), "to_outlet": str(r.to_outlet_id),
            "menu_item": str(r.menu_item_id), "status": r.status, "mode": r.mode,
            "dispatched": str(r.dispatched_quantity), "posted": str(r.posted_quantity),
            "outstanding": str(r.outstanding_quantity),
        } for r in transfers])

    @action(detail=False, methods=["post"], url_path="receive")
    def receive(self, request):
        try:
            receipt_id = uuid.UUID(str(request.data.get("receipt_id")))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationError({"receipt_id": "Invalid transfer reference."}) from exc
        receipt = StockTransferReceipt.objects.filter(
            id=receipt_id, tenant=request.tenant,
            to_outlet_id__in=membership_outlet_ids(request.tenant_membership),
        ).first()
        if receipt is None:
            raise ValidationError({"receipt_id": "Transfer is not accessible."})
        result = verify_stock_transfer_receipt(
            receipt=receipt, membership=request.tenant_membership, user=request.user,
            received_quantity=request.data.get("received_quantity"),
            note=request.data.get("note", ""),
        )
        return Response({
            "status": result.status, "posted": str(result.posted_quantity),
            "outstanding": str(result.outstanding_quantity),
        })

    @action(detail=False, methods=["post"], url_path="resolve")
    def resolve(self, request):
        try:
            receipt_id = uuid.UUID(str(request.data.get("receipt_id")))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationError({"receipt_id": "Invalid transfer reference."}) from exc
        ids = membership_outlet_ids(request.tenant_membership)
        receipt = StockTransferReceipt.objects.filter(
            id=receipt_id, tenant=request.tenant,
            from_outlet_id__in=ids, to_outlet_id__in=ids,
        ).first()
        if receipt is None:
            raise ValidationError({"receipt_id": "Transfer is not accessible."})
        result = resolve_stock_transfer_discrepancy(
            receipt=receipt, membership=request.tenant_membership, user=request.user,
            action=request.data.get("action", ""), note=request.data.get("note", ""),
        )
        return Response({
            "status": result.status, "posted": str(result.posted_quantity),
            "returned": str(result.returned_quantity),
            "written_off": str(result.written_off_quantity),
        })


class StockCountSessionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole, CanViewInventory]
    required_staff_module = "inventory"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockCountSession.objects.none()
        qs = (
            StockCountSession.objects.filter(
                tenant=self.request.tenant,
                outlet_id__in=membership_outlet_ids(self.request.tenant_membership),
            )
            .select_related("outlet", "created_by")
            .prefetch_related("lines__menu_item")
        )
        outlet = self.request.query_params.get("outlet")
        if outlet:
            try:
                qs = qs.filter(outlet_id=uuid.UUID(str(outlet)))
            except ValueError:
                return StockCountSession.objects.none()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return StockCountSessionCreateSerializer
        return StockCountSessionSerializer

    def _resolve_count_lines(self, request):
        ser = StockCountCompleteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        rows = []
        for row in ser.validated_data["lines"]:
            item = MenuItem.objects.filter(
                id=row["menu_item"], tenant_id=request.tenant.id, is_active=True,
            ).first()
            if item is None:
                raise ValidationError({"lines": "Unknown product in stock count."})
            rows.append({"menu_item": item, "counted_quantity": row["counted_quantity"]})
        return rows

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        session = submit_stock_count_for_review(
            session=self.get_object(), resolved_lines=self._resolve_count_lines(request),
            user=request.user, membership=request.tenant_membership,
        )
        return Response(StockCountSessionSerializer(session, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        session = approve_stock_count_session(
            session=self.get_object(), user=request.user,
            membership=request.tenant_membership,
        )
        return Response(StockCountSessionSerializer(session, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="recount")
    def recount(self, request, pk=None):
        session = return_stock_count_for_recount(
            session=self.get_object(), user=request.user,
            membership=request.tenant_membership, reason=request.data.get("reason", ""),
        )
        return Response(StockCountSessionSerializer(session, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        session = self.get_object()
        if not outlet_belongs_to_membership(request.tenant_membership, session.outlet_id):
            return Response(
                {"error": {"code": "forbidden", "message": "You cannot modify counts for this outlet."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if session.status != StockCountStatus.DRAFT:
            return Response(
                {"error": {"code": "invalid_state", "message": "Only draft sessions can be cancelled."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session.status = StockCountStatus.CANCELLED
        session.save(update_fields=["status", "updated_at"])
        return Response(StockCountSessionSerializer(session, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        session = self.get_object()
        if not outlet_belongs_to_membership(request.tenant_membership, session.outlet_id):
            return Response(
                {"error": {"code": "forbidden", "message": "You cannot modify counts for this outlet."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if session.status != StockCountStatus.DRAFT:
            return Response(
                {"error": {"code": "invalid_state", "message": "Only draft sessions can be completed."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not membership_has_inventory_capability(request.tenant_membership, "approve_count"):
            raise ValidationError("Only managers can directly finalize stock counts.")
        complete_stock_count_session(
            session=session, resolved_lines=self._resolve_count_lines(request),
            user=request.user, membership=request.tenant_membership,
        )
        session = (
            StockCountSession.objects.filter(pk=session.pk)
            .select_related("outlet", "created_by")
            .prefetch_related("lines__menu_item")
            .first()
        )
        return Response(
            StockCountSessionSerializer(session, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
