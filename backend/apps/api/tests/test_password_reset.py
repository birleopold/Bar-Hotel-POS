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
        self.user.is_platform_staff = True  # Eligible operator without tenant membership.
        self.user.save(update_fields=["is_platform_staff"])

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

    def test_used_approval_cannot_reset_twice(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        token = default_token_generator.make_token(self.user)
        approval = PasswordRecoveryRequest.objects.create(
            user=self.user, status="sent", token_digest=sha256(token.encode()).hexdigest(),
            approved_at=timezone.now(), expires_at=timezone.now() + timedelta(minutes=30),
        )
        payload = {"uid": uid, "token": token, "new_password": "BrandNewPass9!"}
        first = self.client.post("/api/v1/auth/password/reset/confirm/", payload, format="json")
        self.assertEqual(first.status_code, 200)
        approval.refresh_from_db()
        self.assertEqual(approval.status, "used")
        self.assertEqual(approval.token_digest, "")
        second = self.client.post("/api/v1/auth/password/reset/confirm/", payload, format="json")
        self.assertEqual(second.status_code, 400)

    def test_expired_approval_rejected(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        token = default_token_generator.make_token(self.user)
        PasswordRecoveryRequest.objects.create(
            user=self.user, status="sent", token_digest=sha256(token.encode()).hexdigest(),
            approved_at=timezone.now() - timedelta(hours=1),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        resp = self.client.post("/api/v1/auth/password/reset/confirm/", {
            "uid": uid, "token": token, "new_password": "BrandNewPass9!",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_disabled_worker_cannot_request_or_use_reset_link(self) -> None:
        from apps.tenants.models import Tenant
        from apps.accounts.models import Membership, MembershipRole
        tenant = Tenant.objects.create(name="Closed Shop", slug="closed-shop-reset")
        self.user.is_platform_staff = False
        self.user.save(update_fields=["is_platform_staff"])
        Membership.objects.create(
            tenant=tenant, user=self.user, role=MembershipRole.SERVER, is_active=False
        )
        response = self.client.post(
            "/api/v1/auth/password/reset/", {"email": self.user.email}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.assertFalse(PasswordRecoveryRequest.objects.filter(user=self.user).exists())
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        token = default_token_generator.make_token(self.user)
        PasswordRecoveryRequest.objects.create(
            user=self.user, status="sent", token_digest=sha256(token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        attempt = self.client.post("/api/v1/auth/password/reset/confirm/", {
            "uid": uid, "token": token, "new_password": "BrandNewPass9!"
        }, format="json")
        self.assertEqual(attempt.status_code, 400)
