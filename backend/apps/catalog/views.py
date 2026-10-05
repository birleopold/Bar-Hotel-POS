import uuid

from django.db import transaction
from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import HasTenantContext, HasTenantModule, NotReadOnlyRole
from apps.pos.menu_cache import menu_items_for_outlet_queryset_cached
from apps.pos.services import menu_items_for_outlet_queryset

from .modifier_serializers import ModifierGroupSerializer, ModifierOptionSerializer
from .models import MenuCategory, MenuItem, ModifierGroup, ModifierOption, Promotion
from .recipe_promo_serializers import (
    MenuItemRecipeLineReadSerializer,
    MenuItemRecipeReplaceSerializer,
    PromotionSerializer,
)
from .serializers import MenuCategorySerializer, MenuItemListSerializer, MenuItemSerializer


class MenuCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"
    serializer_class = MenuCategorySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MenuCategory.objects.none()
        return MenuCategory.objects.filter(tenant=self.request.tenant).order_by(
            "sort_order", "name"
        )

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class MenuItemViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MenuItem.objects.none()
        tenant = self.request.tenant
        outlet_param = self.request.query_params.get("outlet")
        if outlet_param:
            try:
                oid = uuid.UUID(str(outlet_param))
            except ValueError:
                return MenuItem.objects.none()
            if (
                getattr(self, "action", None) == "list"
                and not self.request.query_params.get("barcode")
                and not self.request.query_params.get("sku")
            ):
                qs = menu_items_for_outlet_queryset_cached(tenant.id, oid)
            else:
                qs = menu_items_for_outlet_queryset(tenant.id, oid)
        else:
            qs = MenuItem.objects.filter(tenant=tenant).select_related("category").prefetch_related(
                "outlet_links__outlet"
            )

        barcode = self.request.query_params.get("barcode")
        if barcode:
            qs = qs.filter(barcode=barcode.strip())
        sku = self.request.query_params.get("sku")
        if sku:
            qs = qs.filter(sku=sku.strip())

        return qs.order_by("category__sort_order", "category__name", "name")

    def get_serializer_class(self):
        if self.action == "list":
            return MenuItemListSerializer
        return MenuItemSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        op = self.request.query_params.get("outlet")
        if op:
            try:
                ctx["outlet_id"] = uuid.UUID(str(op))
            except ValueError:
                pass
        return ctx

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)

    @action(detail=False, methods=["get"], url_path="resolve")
    def resolve(self, request):
        """Resolve a single sellable row by barcode (and optional outlet scoping)."""
        barcode = (request.query_params.get("barcode") or "").strip()
        if not barcode:
            return Response(
                {"error": {"code": "barcode_required", "message": "Query parameter barcode is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant = request.tenant
        outlet_param = request.query_params.get("outlet")
        if outlet_param:
            try:
                oid = uuid.UUID(str(outlet_param))
            except ValueError:
                return Response(
                    {"error": {"code": "invalid_outlet", "message": "outlet must be a UUID."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = menu_items_for_outlet_queryset(tenant.id, oid).filter(
                barcode=barcode, is_active=True
            )
            ctx = {**self.get_serializer_context(), "outlet_id": oid}
        else:
            qs = MenuItem.objects.filter(tenant=tenant, barcode=barcode, is_active=True)
            ctx = self.get_serializer_context()
        item = qs.select_related("category").first()
        if item is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ser = MenuItemListSerializer(item, context=ctx)
        return Response(ser.data)

    @action(detail=True, methods=["get", "put"], url_path="recipe")
    def recipe(self, request, pk=None):
        item = self.get_object()
        if request.method == "GET":
            lines = item.recipe_lines.select_related("ingredient_item")
            return Response(MenuItemRecipeLineReadSerializer(lines, many=True).data)
        ser = MenuItemRecipeReplaceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            ser.save(parent_item=item)
        lines = item.recipe_lines.select_related("ingredient_item")
        return Response(MenuItemRecipeLineReadSerializer(lines, many=True).data)


class ModifierGroupViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"
    serializer_class = ModifierGroupSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ModifierGroup.objects.none()
        return (
            ModifierGroup.objects.filter(tenant=self.request.tenant)
            .prefetch_related(
                Prefetch(
                    "options",
                    ModifierOption.objects.filter(is_active=True).order_by("sort_order", "name"),
                )
            )
            .order_by("name")
        )


class ModifierOptionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"
    serializer_class = ModifierOptionSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ModifierOption.objects.none()
        qs = ModifierOption.objects.filter(group__tenant=self.request.tenant).select_related("group")
        g = self.request.query_params.get("group")
        if g:
            try:
                qs = qs.filter(group_id=uuid.UUID(str(g)))
            except ValueError:
                return ModifierOption.objects.none()
        return qs.order_by("group", "sort_order", "name")


class PromotionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, HasTenantModule, NotReadOnlyRole]
    required_staff_module = "pos"
    serializer_class = PromotionSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Promotion.objects.none()
        return Promotion.objects.filter(tenant=self.request.tenant).prefetch_related("outlets").order_by(
            "-starts_at", "name"
        )
