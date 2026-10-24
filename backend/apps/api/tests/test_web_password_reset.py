from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import User, PasswordRecoveryRequest
from hashlib import sha256
from django.utils import timezone
from datetime import timedelta


class StaffPasswordResetPageTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(email="staff-page@example.com", password="OldPassw0rd!")
        self.user.is_platform_staff = True  # Eligible operator without tenant membership.
        self.user.save(update_fields=["is_platform_staff"])

    def test_recovery_templates_use_configured_static_asset(self) -> None:
        from pathlib import Path
        from django.template.loader import get_template
        base = Path(__file__).resolve().parents[3] / "templates/password_reset"
        for page in ("request.html", "confirm.html"):
            with self.subTest(page=page):
                source = (base / page).read_text(encoding="utf-8")
                self.assertIn("{% static 'staff/fizo-auth-2026.css' %}", source)
                self.assertNotIn('href="/static/staff/fizo-auth-2026.css', source)
                get_template("password_reset/" + page)

    def test_shared_recovery_has_no_testing_tenant_brand(self) -> None:
        from pathlib import Path
        base = Path(__file__).resolve().parents[3]
        for page in ("request.html", "confirm.html"):
            with self.subTest(page=page):
                source = (base / "templates/password_reset" / page).read_text(encoding="utf-8")
                self.assertNotIn("· Fizo", source)
                self.assertNotIn('> Fizo</div>', source)
                self.assertIn("POS", source)
        notices = (base / "apps/api/password_reset_core.py").read_text(encoding="utf-8")
        self.assertNotIn("Your Fizo", notices)
        self.assertIn("Your POS account password was changed", notices)

    def test_get_without_query_shows_invalid(self) -> None:
        r = self.client.get("/password-reset/confirm/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "invalid", status_code=200)

    def test_get_with_uid_token_shows_form(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        token = default_token_generator.make_token(self.user)
        r = self.client.get("/password-reset/confirm/", {"uid": uid, "token": token})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "name=")
        self.assertContains(r, "new_password")

    def test_post_updates_password(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        token = default_token_generator.make_token(self.user)
        PasswordRecoveryRequest.objects.create(
            user=self.user, status="sent", token_digest=sha256(token.encode()).hexdigest(),
            approved_at=timezone.now(), expires_at=timezone.now() + timedelta(minutes=30),
        )
        r = self.client.post(
            "/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": "NewStrongPass9!", "confirm_password": "NewStrongPass9!"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Password updated", status_code=200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass9!"))

    def test_post_bad_token_shows_error(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        r = self.client.post(
            "/password-reset/confirm/",
            {"uid": uid, "token": "nope", "new_password": "NewStrongPass9!", "confirm_password": "NewStrongPass9!"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Invalid or expired", status_code=200)

    def test_request_page_stages_without_sending_password_link(self):
        from django.core import mail
        from django.test import override_settings
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self.client.post("/password-reset/", {"email": self.user.email})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "received for review")
        self.assertTrue(PasswordRecoveryRequest.objects.filter(user=self.user, status="pending").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_unapproved_token_cannot_reset_password(self):
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        token = default_token_generator.make_token(self.user)
        response = self.client.post("/password-reset/confirm/", {
            "uid": uid, "token": token, "new_password": "NewStrongPass9!",
            "confirm_password": "NewStrongPass9!",
        })
        self.assertContains(response, "Invalid or expired")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPassw0rd!"))
