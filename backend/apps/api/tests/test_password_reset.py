from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.accounts.models import User, PasswordRecoveryRequest
from hashlib import sha256
from django.utils import timezone
from datetime import timedelta


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user = User.objects.create_user(email="reset-user@example.com", password="InitialPass9!")

    def test_request_unknown_email_still_202_no_mail(self) -> None:
        r = self.client.post(
            "/api/v1/auth/password/reset/",
            {"email": "nobody@example.com"},
            format="json",
        )
        self.assertEqual(r.status_code, 202)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_known_user_requires_admin_approval(self) -> None:
        r = self.client.post(
            "/api/v1/auth/password/reset/",
            {"email": "reset-user@example.com"},
            format="json",
        )
        self.assertEqual(r.status_code, 202)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(PasswordRecoveryRequest.objects.filter(user=self.user, status="pending").exists())

    def test_confirm_invalid_token(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        r = self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {"uid": uid, "token": "invalid", "new_password": "BrandNewPass9!"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_confirm_success_updates_password(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        token = default_token_generator.make_token(self.user)
        PasswordRecoveryRequest.objects.create(
            user=self.user, status="sent", token_digest=sha256(token.encode()).hexdigest(),
            approved_at=timezone.now(), expires_at=timezone.now() + timedelta(minutes=30),
        )
        r = self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {"uid": uid, "token": token, "new_password": "BrandNewPass9!"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPass9!"))
