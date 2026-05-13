import uuid

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.access.outlets import outlet_belongs_to_membership
from apps.api.permissions import HasTenantContext, NotReadOnlyRole
from apps.tenants.models import Outlet

from .services.catalog_version import catalog_version_payload


class PosCatalogVersionView(APIView):
    """
    Outlet-scoped catalog fingerprint for offline POS clients.

    Poll or use before replaying queued ``order_create`` mutations; send the token back
    as ``payload.catalog_version`` on offline sync to get ``409 catalog_stale`` when the
    menu changed while offline.
    """

    permission_classes = [IsAuthenticated, HasTenantContext, NotReadOnlyRole]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "catalog_version"

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="outlet",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Outlet UUID within the tenant",
            ),
        ],
        responses={200: dict},
    )
    def get(self, request: Request) -> Response:
        raw = (request.query_params.get("outlet") or "").strip()
        if not raw:
            return Response(
                {"error": {"code": "outlet_required", "message": "Query parameter outlet is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            oid = uuid.UUID(str(raw))
        except ValueError:
            return Response(
                {"error": {"code": "invalid_outlet", "message": "outlet must be a UUID."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        outlet = Outlet.objects.filter(
            id=oid,
            site__tenant_id=request.tenant.id,
            is_active=True,
        ).first()
        if outlet is None:
            return Response(
                {"error": {"code": "invalid_outlet", "message": "Invalid outlet."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not outlet_belongs_to_membership(request.tenant_membership, outlet.id):
            return Response(
                {
                    "error": {
                        "code": "outlet_forbidden",
                        "message": "You cannot read catalog for this outlet.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        body = catalog_version_payload(tenant_id=request.tenant.id, outlet_id=outlet.id)
        body["outlet"] = str(outlet.id)
        return Response(body, status=status.HTTP_200_OK)
