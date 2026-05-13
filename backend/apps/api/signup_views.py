from __future__ import annotations

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.tenants.business_lines import normalize_business_lines

from .signup_service import create_pending_workspace_signup


_SignupRequest = inline_serializer(
    "SignupRequest",
    fields={
        "email": serializers.EmailField(),
        "password": serializers.CharField(),
        "workspace_name": serializers.CharField(),
        "business_lines": serializers.ListField(
            child=serializers.CharField(),
            required=False,
            allow_empty=True,
        ),
    },
)

_SignupResponse = inline_serializer(
    "SignupResponse",
    fields={
        "user_id": serializers.UUIDField(),
        "tenant_id": serializers.UUIDField(),
        "message": serializers.CharField(),
    },
)


class PublicSignupView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_signup"

    @extend_schema(request=_SignupRequest, responses={201: _SignupResponse}, auth=[])
    def post(self, request) -> Response:
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""
        workspace_name = (request.data.get("workspace_name") or "").strip()
        business_lines = normalize_business_lines(request.data.get("business_lines"))

        if not email:
            return Response(
                {"error": {"code": "email_required", "message": "email is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not workspace_name:
            return Response(
                {
                    "error": {
                        "code": "workspace_name_required",
                        "message": "workspace_name is required.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not password or len(password) < 8:
            return Response(
                {
                    "error": {
                        "code": "weak_password",
                        "message": "Password must be at least 8 characters.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not business_lines:
            return Response(
                {
                    "error": {
                        "code": "business_lines_required",
                        "message": "Choose at least one business line.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {
                    "error": {
                        "code": "email_in_use",
                        "message": "An account with this email already exists.",
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        user, tenant = create_pending_workspace_signup(
            email=email,
            password=password,
            workspace_name=workspace_name,
            business_lines=business_lines,
        )

        return Response(
            {
                "user_id": str(user.id),
                "tenant_id": str(tenant.id),
                "message": "Account created. Your workspace is pending platform approval.",
            },
            status=status.HTTP_201_CREATED,
        )
