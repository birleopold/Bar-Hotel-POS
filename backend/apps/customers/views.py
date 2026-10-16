"""Read-only customer lookup for authorized client workflows.

Mutations, merges and financial changes remain in the audited domain/staff
workflows. This API reuses precisely the same tenant/branch visibility rule.
"""
from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from apps.api.permissions import HasTenantContext
from apps.staff.services.customers import can_manage_customers, visible_customers

from .models import Customer


class CustomerDirectorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone", "preferences")
        read_only_fields = fields


class CustomerDirectoryPagination(PageNumberPagination):
    page_size = 30
    max_page_size = 50
    page_size_query_param = "page_size"


class CustomerDirectoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Tenant-scoped directory and detail, no unscoped customer disclosure."""

    serializer_class = CustomerDirectorySerializer
    permission_classes = (IsAuthenticated, HasTenantContext)
    pagination_class = CustomerDirectoryPagination
    http_method_names = ("get", "head", "options")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Customer.objects.none()
        membership = getattr(self.request, "tenant_membership", None)
        if membership is None or not can_manage_customers(membership):
            raise PermissionDenied("Your role cannot view customer profiles.")
        qs = visible_customers(membership, self.request.user)
        query = (self.request.query_params.get("q") or "").strip()[:100]
        if query:
            qs = qs.filter(
                Q(name__icontains=query) | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )
        return qs.order_by("name", "id")
