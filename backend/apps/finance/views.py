from __future__ import annotations

import uuid

from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.api.permissions import HasTenantContext, NotReadOnlyRole

from .models import CashbookEntry, FinanceCategory
from .serializers import CashbookEntrySerializer, FinanceCategorySerializer


class FinanceCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = FinanceCategorySerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FinanceCategory.objects.none()
        qs = FinanceCategory.objects.filter(tenant=self.request.tenant)
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind.strip())
        active = self.request.query_params.get("active")
        if active and active.strip().lower() in {"1", "true", "yes"}:
            qs = qs.filter(is_active=True)
        return qs.order_by("kind", "sort_order", "name")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class CashbookEntryViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = CashbookEntrySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CashbookEntry.objects.none()
        membership = self.request.tenant_membership
        qs = CashbookEntry.objects.filter(tenant=self.request.tenant).select_related(
            "category", "site", "created_by"
        )
        if membership.sites.exists():
            allowed_site_ids = membership.sites.values_list("pk", flat=True)
            qs = qs.filter(Q(site__isnull=True) | Q(site_id__in=allowed_site_ids))
        site_param = self.request.query_params.get("site")
        if site_param:
            try:
                qs = qs.filter(site_id=uuid.UUID(str(site_param)))
            except ValueError:
                return CashbookEntry.objects.none()
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(category__kind=kind.strip())
        return qs.order_by("-transaction_date", "-created_at")
