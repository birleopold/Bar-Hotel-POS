"""Shared password-reset confirmation (API + HTML form)."""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from apps.accounts.models import User


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)


def attempt_password_reset_confirm(*, uid: str, token: str, new_password: str) -> tuple[int, dict]:
    """
    Validate uid/token and set password. Returns (HTTP status, body dict) matching the JSON API shape.
    """
    ser = PasswordResetConfirmSerializer(
        data={"uid": uid or "", "token": token or "", "new_password": new_password or ""}
    )
    if not ser.is_valid():
        return 400, {
            "error": {
                "code": "invalid_input",
                "message": "Invalid input.",
                "fields": ser.errors,
            }
        }
    vd = ser.validated_data
    try:
        raw = force_str(urlsafe_base64_decode(vd["uid"]))
        user = User.objects.get(pk=raw, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return 400, {
            "error": {"code": "invalid_reset", "message": "Invalid or expired reset link."},
        }
    if not default_token_generator.check_token(user, vd["token"]):
        return 400, {
            "error": {"code": "invalid_reset", "message": "Invalid or expired reset link."},
        }
    try:
        validate_password(vd["new_password"], user=user)
    except ValidationError as exc:
        return 400, {
            "error": {
                "code": "validation_error",
                "message": "Password does not meet requirements.",
                "fields": {"new_password": list(exc.messages)},
            }
        }
    user.set_password(vd["new_password"])
    user.save(update_fields=["password"])
    return 200, {"detail": "Password updated. You can sign in with your new password."}
