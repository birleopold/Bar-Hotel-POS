from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import User


class StaffPasswordResetPageTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(email="staff-page@example.com", password="OldPassw0rd!")

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
        r = self.client.post(
            "/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": "NewStrongPass9!"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Password updated", status_code=200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass9!"))

    def test_post_bad_token_shows_error(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        r = self.client.post(
            "/password-reset/confirm/",
            {"uid": uid, "token": "nope", "new_password": "NewStrongPass9!"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Invalid or expired", status_code=200)
