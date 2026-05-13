"""Password reset for API clients (JWT users). Uses Django's token generator."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User

from .password_reset_core import PasswordResetConfirmSerializer, attempt_password_reset_confirm


class PasswordResetRequestThrottle(AnonRateThrottle):
    rate = "5/minute"


class PasswordResetConfirmThrottle(AnonRateThrottle):
    rate = "20/minute"


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


def _uid_b64(user: User) -> str:
    return urlsafe_base64_encode(force_bytes(str(user.pk)))


def build_password_reset_email_body(*, user_email: str, uid: str, token: str) -> str:
    """Plain-text body for password reset (used synchronously or from Celery)."""
    template = getattr(settings, "PASSWORD_RESET_URL_TEMPLATE", "") or ""
    if template.strip():
        try:
            link = template.format(uid=uid, token=token)
        except (KeyError, ValueError):
            link = f"{template.rstrip('?&')}?uid={uid}&token={token}"
        return (
            f"You requested a password reset for {user_email}.\n\n"
            f"Open this link to choose a new password (or paste uid/token into your app):\n{link}\n\n"
            "If you did not request this, ignore this email."
        )
    return (
        f"Password reset for {user_email}.\n\n"
        "Open the staff reset page (replace host with your server):\n"
        f"  /password-reset/confirm/?uid={uid}&token={token}\n\n"
        "Or POST JSON to /api/v1/auth/password/reset/confirm/ with uid, token, new_password.\n\n"
        "If you did not request this, ignore this email."
    )


def _send_reset_email_sync(*, user: User, uid: str, token: str) -> None:
    body = build_password_reset_email_body(user_email=user.email, uid=uid, token=token)
    send_mail(
        subject=getattr(settings, "PASSWORD_RESET_EMAIL_SUBJECT", "Password reset"),
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def _dispatch_password_reset_email(*, user: User, uid: str, token: str) -> None:
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", True):
        _send_reset_email_sync(user=user, uid=uid, token=token)
        return
    from .tasks import send_password_reset_email_task

    send_password_reset_email_task.delay(user_email=user.email, uid_b64=uid, token=token)


def request_password_reset_for_email(*, email: str) -> None:
    """Issue reset email when account exists; silent for unknown email."""
    normalized = (email or "").strip().lower()
    user = User.objects.filter(email__iexact=normalized, is_active=True).first()
    if user is None:
        return
    token = default_token_generator.make_token(user)
    uid = _uid_b64(user)
    _dispatch_password_reset_email(user=user, uid=uid, token=token)


@extend_schema(
    request=PasswordResetRequestSerializer,
    responses={
        202: inline_serializer(
            "PasswordResetAccepted",
            fields={"detail": serializers.CharField()},
        ),
    },
    auth=[],
)
class PasswordResetRequestView(APIView):
    """Request a reset email. Response is always the same to avoid account enumeration."""

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRequestThrottle]

    def post(self, request: Request) -> Response:
        ser = PasswordResetRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        request_password_reset_for_email(email=ser.validated_data["email"])
        return Response(
            {"detail": "If an account exists for this email, password reset instructions were sent."},
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema(
    request=PasswordResetConfirmSerializer,
    responses={
        200: inline_serializer(
            "PasswordResetDone",
            fields={"detail": serializers.CharField()},
        ),
    },
    auth=[],
)
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetConfirmThrottle]

    def post(self, request: Request) -> Response:
        data = request.data
        status_code, body = attempt_password_reset_confirm(
            uid=str(data.get("uid", "")),
            token=str(data.get("token", "")),
            new_password=str(data.get("new_password", "")),
        )
        return Response(body, status=status_code)
