"""Shared password-reset confirmation (API + HTML form)."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.db import transaction
from hashlib import sha256
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from apps.accounts.models import User, PasswordRecoveryRequest


def recovery_eligible(user: User) -> bool:
    """Only current workers or platform operators may recover account access."""
    return bool(
        user.is_active
        and (
            user.is_superuser or user.is_platform_staff
            or user.memberships.filter(is_active=True, tenant__is_active=True).exists()
        )
    )


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
    if not recovery_eligible(user):
        return 400, {"error": {"code": "invalid_reset", "message": "Invalid or expired reset link."}}
    digest = sha256(vd["token"].encode()).hexdigest()
    approval = PasswordRecoveryRequest.objects.filter(
        user=user, status="sent", token_digest=digest, expires_at__gt=timezone.now()
    ).order_by("-approved_at").first()
    if approval is None:
        return 400, {"error": {"code": "invalid_reset", "message": "Invalid or expired reset link."}}
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
    with transaction.atomic():
        approved = PasswordRecoveryRequest.objects.select_for_update().filter(
            pk=approval.pk, status="sent", token_digest=digest,
            expires_at__gt=timezone.now()
        ).first()
        if approved is None:
            return 400, {"error": {"code": "invalid_reset", "message": "Invalid or expired reset link."}}
        user.set_password(vd["new_password"])
        user.save(update_fields=["password"])
        approved.status = "used"
        approved.token_digest = ""
        approved.save(update_fields=["status", "token_digest"])
        # No credentials in the notice; recovery itself never logs the user in.
        transaction.on_commit(lambda recipient=user.email: send_mail(
            "Your POS account password was changed",
            "The password for your POS account has been updated. "
            "If you did not authorize this, contact your platform administrator immediately.",
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=True,
        ))
    return 200, {"detail": "Password updated. You can sign in with your new password."}
