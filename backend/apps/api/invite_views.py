from __future__ import annotations

import hashlib

from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.invite_service import create_user_invite
from apps.accounts.models import Membership, MembershipRole, User, UserInvite
from apps.api.permissions import CanManageTenantSettings, HasTenantContext, NotReadOnlyRole
from apps.tenants.models import Outlet, Site

_InviteCreateRequest = inline_serializer(
    "InviteCreateRequest",
    fields={
        "email": serializers.EmailField(),
        "role": serializers.CharField(required=False),
        "expires_days": serializers.IntegerField(required=False),
        "site_ids": serializers.ListField(child=serializers.UUIDField(), allow_empty=False),
        "outlet_ids": serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True),
    },
)
_InviteCreated = inline_serializer(
    "InviteCreated",
    fields={
        "id": serializers.UUIDField(),
        "email": serializers.EmailField(),
        "role": serializers.CharField(),
        "expires_at": serializers.DateTimeField(),
        "token": serializers.CharField(),
    },
)
_InviteAcceptRequest = inline_serializer(
    "InviteAcceptRequest",
    fields={
        "token": serializers.CharField(),
        "password": serializers.CharField(),
    },
)
_InviteAccepted = inline_serializer(
    "InviteAccepted",
    fields={
        "email": serializers.EmailField(),
        "tenant_id": serializers.UUIDField(),
        "message": serializers.CharField(),
    },
)


class InviteCreateView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasTenantContext,
        CanManageTenantSettings,
        NotReadOnlyRole,
    ]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invite_create"

    @extend_schema(request=_InviteCreateRequest, responses={201: _InviteCreated})
    def post(self, request: Request) -> Response:
        email = (request.data.get("email") or "").strip().lower()
        role = request.data.get("role") or MembershipRole.SERVER
        expires_days = int(request.data.get("expires_days") or 7)
        site_ids = request.data.get("site_ids") or []
        outlet_ids = request.data.get("outlet_ids") or []
        if not email:
            return Response(
                {"error": {"code": "email_required", "message": "email is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role not in {c.value for c in MembershipRole}:
            return Response(
                {"error": {"code": "invalid_role", "message": "Invalid role."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
            return Response(
                {"error": {"code": "invalid_role", "message": "Owner and tenant admin roles cannot be assigned by invitation."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not site_ids:
            return Response(
                {"error": {"code": "site_required", "message": "Assign at least one branch to this worker."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sites = list(Site.objects.filter(tenant=request.tenant, is_active=True, pk__in=site_ids))
        if len({str(site.pk) for site in sites}) != len({str(site_id) for site_id in site_ids}):
            return Response({"error": {"code": "invalid_site", "message": "A selected branch is outside this workspace."}}, status=status.HTTP_400_BAD_REQUEST)
        outlets = list(Outlet.objects.filter(site__tenant=request.tenant, site_id__in=site_ids, is_active=True, site__is_active=True, pk__in=outlet_ids))
        if len({str(outlet.pk) for outlet in outlets}) != len({str(outlet_id) for outlet_id in outlet_ids}):
            return Response({"error": {"code": "invalid_outlet", "message": "A selected outlet is outside the assigned branches."}}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from apps.tenants.business_lines import normalize_business_lines, outlet_types_for_business_lines

            configured_lines = normalize_business_lines(request.tenant.settings.business_lines)
        except Exception:
            configured_lines = []
        if not configured_lines:
            return Response({"error": {"code": "business_lines_required", "message": "Configure a business line before inviting workers."}}, status=status.HTTP_400_BAD_REQUEST)
        allowed_types = set(outlet_types_for_business_lines(configured_lines))
        if any(outlet.outlet_type not in allowed_types for outlet in outlets):
            return Response({"error": {"code": "invalid_outlet", "message": "A selected outlet is outside this workspace's configured services."}}, status=status.HTTP_400_BAD_REQUEST)
        if any(not any(outlet.site_id == site.pk and outlet.outlet_type in allowed_types for outlet in outlets) for site in sites):
            return Response({"error": {"code": "invalid_site", "message": "Each assigned branch must contain an outlet in this workspace's configured services."}}, status=status.HTTP_400_BAD_REQUEST)
        from apps.staff.services.membership import ROLE_OUTLET_TYPES

        role_types = ROLE_OUTLET_TYPES.get(role)
        if outlets and role_types and any(outlet.outlet_type not in role_types for outlet in outlets):
            return Response({"error": {"code": "invalid_outlet", "message": "A selected outlet does not match this worker's role."}}, status=status.HTTP_400_BAD_REQUEST)
        inv, raw = create_user_invite(
            tenant=request.tenant,
            email=email,
            role=role,
            expires_days=expires_days,
            invited_by=request.user,
        )
        inv.sites.set(sites)
        inv.outlets.set(outlets)
        return Response(
            {
                "id": str(inv.id),
                "email": inv.email,
                "role": inv.role,
                "expires_at": inv.expires_at.isoformat(),
                "token": raw,
            },
            status=status.HTTP_201_CREATED,
        )


class InviteAcceptView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invite_accept"

    @extend_schema(
        request=_InviteAcceptRequest,
        responses={200: _InviteAccepted},
        auth=[],
    )
    def post(self, request: Request) -> Response:
        token = (request.data.get("token") or "").strip()
        password = request.data.get("password") or ""
        if not token or not password:
            return Response(
                {"error": {"code": "fields_required", "message": "token and password are required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(password) < 8:
            return Response(
                {"error": {"code": "weak_password", "message": "Password must be at least 8 characters."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        h = hashlib.sha256(token.encode()).hexdigest()
        inv = UserInvite.objects.filter(token_hash=h, accepted_at__isnull=True).select_related("tenant").first()
        if inv is None or inv.expires_at < timezone.now():
            return Response(
                {"error": {"code": "invalid_invite", "message": "Invite is invalid or expired."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = inv.email.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is not None and Membership.objects.filter(user=user, tenant=inv.tenant).exists():
            return Response(
                {"error": {"code": "membership_exists", "message": "This user already belongs to the workspace. Ask an administrator to update their access."}},
                status=status.HTTP_409_CONFLICT,
            )
        if user is None:
            user = User.objects.create_user(email=email, password=password)
        else:
            user.set_password(password)
            user.save(update_fields=["password"])
        membership, created = Membership.objects.get_or_create(
            user=user,
            tenant=inv.tenant,
            defaults={"role": inv.role, "is_active": True},
        )
        if created:
            membership.sites.set(inv.sites.all())
            membership.outlets.set(inv.outlets.all())
        inv.accepted_at = timezone.now()
        inv.save(update_fields=["accepted_at", "updated_at"])
        return Response(
            {
                "email": user.email,
                "tenant_id": str(inv.tenant_id),
                "message": "Account ready. Obtain JWT via /api/v1/auth/token/.",
            },
            status=status.HTTP_200_OK,
        )
