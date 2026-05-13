from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantSettings

from .permissions import CanManageTenantSettings, HasTenantContext, NotReadOnlyRole
from .serializers import MeSerializer, TenantSettingsSerializer


@extend_schema(
    responses={
        200: inline_serializer(
            "HealthOk",
            fields={"status": serializers.CharField()},
        ),
    },
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(_request: Request) -> Response:
    return Response({"status": "OK"})


@extend_schema(responses=MeSerializer)
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = MeSerializer(request.user, context={"request": request})
        return Response(serializer.data)


class TenantSettingsView(APIView):
    """Branding and regional defaults for the active tenant (``X-Tenant-Id``)."""

    def get_permissions(self):
        perms: list = [IsAuthenticated(), HasTenantContext()]
        if self.request.method != "GET":
            perms.extend([CanManageTenantSettings(), NotReadOnlyRole()])
        return perms

    @extend_schema(responses=TenantSettingsSerializer)
    def get(self, request: Request) -> Response:
        ts, _ = TenantSettings.objects.get_or_create(tenant=request.tenant)
        return Response(TenantSettingsSerializer(ts).data)

    @extend_schema(
        request=TenantSettingsSerializer,
        responses=TenantSettingsSerializer,
    )
    def patch(self, request: Request) -> Response:
        ts, _ = TenantSettings.objects.get_or_create(tenant=request.tenant)
        serializer = TenantSettingsSerializer(ts, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
