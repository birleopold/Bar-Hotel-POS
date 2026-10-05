from __future__ import annotations

import uuid

from rest_framework import mixins, viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.accounts.models import MembershipRole
from apps.api.permissions import HasTenantContext, NotReadOnlyRole
from apps.staff.services.modules import get_tenant_staff_modules
from apps.tenants.business_lines import normalize_business_lines

from .models import CashbookEntry, FinanceCategory
from .serializers import CashbookEntrySerializer, FinanceCategorySerializer


class FinanceCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    serializer_class = FinanceCategorySerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsAuthenticated(), HasTenantContext(), NotReadOnlyRole(), FinanceModuleEnabled(), CanManageFinance()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FinanceCategory.objects.none()
        qs = FinanceCategory.objects.filter(tenant=self.request.tenant)
        if not _tenant_has_finance(self.request.tenant):
            return FinanceCategory.objects.none()
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

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), HasTenantContext(), NotReadOnlyRole(), FinanceModuleEnabled(), CanManageFinance()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CashbookEntry.objects.none()
        membership = self.request.tenant_membership
        qs = CashbookEntry.objects.filter(tenant=self.request.tenant).select_related(
            "category", "site", "created_by"
        )
        if not _tenant_has_finance(self.request.tenant):
            return CashbookEntry.objects.none()
        if membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER) or membership.sites.exists():
            allowed_site_ids = membership.sites.values_list("pk", flat=True)
            qs = qs.filter(site_id__in=allowed_site_ids)
        if membership.role == MembershipRole.CLEANER:
            qs = qs.none()
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


def _tenant_has_finance(tenant):
    try:
        return "finance" in get_tenant_staff_modules(tenant)
    except Exception:
        return False


class FinanceModuleEnabled(BasePermission):
    message = "Finance is not enabled for this workspace."

    def has_permission(self, request, view):
        return _tenant_has_finance(request.tenant)


class CanManageFinance(BasePermission):
    message = "Your role cannot modify finance records."

    def has_permission(self, request, view):
        return request.tenant_membership.role in (
            MembershipRole.OWNER,
            MembershipRole.TENANT_ADMIN,
            MembershipRole.SITE_MANAGER,
        )
