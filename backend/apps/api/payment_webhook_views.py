"""Inbound payment-provider webhooks (MoMo, cards, etc.) — audit + idempotency stub."""

from __future__ import annotations

import json
import uuid

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_audit
from apps.tenants.models import Tenant


class PaymentProviderWebhookView(APIView):
    """
    ``POST`` with JSON body containing at least **event_id**, **provider**, **status**.
    Requires header **X-Tenant-Id** and **X-Webhook-Secret** matching
    ``PAYMENT_WEBHOOK_SHARED_SECRET`` when that setting is non-empty.
    Idempotent per tenant + **event_id** (~30 days).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
        parameters=[
            OpenApiParameter(
                name="X-Tenant-Id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.HEADER,
                required=True,
            ),
            OpenApiParameter(
                name="X-Webhook-Secret",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                required=True,
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        secret = getattr(settings, "PAYMENT_WEBHOOK_SHARED_SECRET", "") or ""
        if not secret.strip():
            return Response(
                {
                    "error": {
                        "code": "webhook_not_configured",
                        "message": "PAYMENT_WEBHOOK_SHARED_SECRET is not set on the server.",
                    }
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if request.headers.get("X-Webhook-Secret") != secret.strip():
            return Response(
                {"error": {"code": "forbidden", "message": "Invalid webhook secret."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_raw = request.headers.get("X-Tenant-Id")
        if not tenant_raw:
            return Response(
                {"error": {"code": "tenant_required", "message": "Header X-Tenant-Id is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            tenant_uuid = uuid.UUID(str(tenant_raw).strip())
        except ValueError:
            return Response(
                {"error": {"code": "invalid_tenant", "message": "X-Tenant-Id must be a UUID."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not Tenant.objects.filter(id=tenant_uuid).exists():
            return Response(
                {"error": {"code": "unknown_tenant", "message": "Tenant not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            body = request.data if isinstance(request.data, dict) else json.loads(request.body)
        except (json.JSONDecodeError, TypeError):
            return Response(
                {"error": {"code": "invalid_json", "message": "Body must be JSON."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        event_id = (body.get("event_id") or body.get("id") or "").strip()
        if not event_id:
            return Response(
                {"error": {"code": "event_id_required", "message": "event_id is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cache_key = f"payment_webhook:{tenant_uuid}:{event_id}"
        if not cache.add(cache_key, "1", timeout=86400 * 30):
            return Response({"ok": True, "replay": True}, status=status.HTTP_200_OK)

        log_audit(
            tenant_id=tenant_uuid,
            user_id=None,
            action="integrations.payment_webhook_received",
            entity_type="payment_webhook",
            entity_id=event_id[:128],
            payload={
                "provider": str(body.get("provider", ""))[:64],
                "status": str(body.get("status", ""))[:64],
                "raw_keys": list(body.keys())[:40],
            },
            source="system",
        )
        return Response({"ok": True, "replay": False}, status=status.HTTP_200_OK)
