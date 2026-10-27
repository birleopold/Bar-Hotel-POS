from __future__ import annotations

from django.http import JsonResponse
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.pos.services.hardware_bridge import (
    authenticate_bridge_token,
    claim_bridge_commands,
    report_bridge_command,
)


def _bridge_token(request):
    token = (request.headers.get("X-Hardware-Bridge-Token") or "").strip()
    if not token:
        raise AuthenticationFailed("Hardware bridge credential required.")
    return token


def _credential(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        raise AuthenticationFailed("Tenant workspace is required.")
    return authenticate_bridge_token(
        tenant_id=tenant.pk,
        token=_bridge_token(request),
    )


class HardwareBridgePollView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        credential = _credential(request)
        try:
            limit = int(request.data.get("limit", 10))
        except (TypeError, ValueError):
            raise ValidationError({"limit": "Use a whole-number claim limit."})
        commands = claim_bridge_commands(
            credential=credential,
            limit=limit,
        )
        return JsonResponse(
            {
                "workstation_id": str(credential.workstation_id),
                "commands": [
                    {
                        "id": str(command.pk),
                        "device_id": str(command.device_id),
                        "device_type": command.device.device_type,
                        "device_label": command.device.label,
                        "command_type": command.command_type,
                        "attempt": command.attempts,
                        "max_attempts": command.max_attempts,
                        "expires_at": command.expires_at.isoformat(),
                        "payload": command.payload,
                    }
                    for command in commands
                ],
            }
        )


class HardwareBridgeReportView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        credential = _credential(request)
        command_id = request.data.get("command_id")
        if not command_id:
            raise ValidationError({"command_id": "Command id is required."})
        success = request.data.get("success")
        if not isinstance(success, bool):
            raise ValidationError({"success": "Use true or false."})
        latency = request.data.get("latency_ms")
        try:
            latency = int(latency) if latency is not None else None
        except (TypeError, ValueError):
            raise ValidationError({"latency_ms": "Use latency in milliseconds."})
        command = report_bridge_command(
            credential=credential,
            command_id=command_id,
            success=success,
            result=request.data.get("result") or {},
            error=str(request.data.get("error") or ""),
            latency_ms=latency,
        )
        return JsonResponse(
            {
                "command_id": str(command.pk),
                "status": command.status,
                "attempts": command.attempts,
                "retry_after": (
                    command.not_before.isoformat()
                    if command.not_before else None
                ),
            }
        )
