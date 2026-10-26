from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.tenants.models import Tenant


class PaymentProviderWebhookTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name="Webhook Tenant", slug="webhook-tenant")
        self.url = reverse("integrations-payment-webhook")
        self.headers = {
            "HTTP_X_TENANT_ID": str(self.tenant.pk),
            "HTTP_X_WEBHOOK_SECRET": "test-webhook-secret",
        }

    def tearDown(self):
        cache.clear()
        super().tearDown()

    @override_settings(PAYMENT_WEBHOOK_SHARED_SECRET="")
    def test_webhook_fails_closed_when_secret_is_not_configured(self):
        response = self.client.post(
            self.url,
            {"event_id": "evt-missing-secret", "provider": "test", "status": "paid"},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "webhook_not_configured")

    @override_settings(PAYMENT_WEBHOOK_SHARED_SECRET="test-webhook-secret")
    def test_webhook_rejects_wrong_secret_and_oversized_event_id(self):
        wrong = dict(self.headers)
        wrong["HTTP_X_WEBHOOK_SECRET"] = "wrong"
        denied = self.client.post(
            self.url,
            {"event_id": "evt-wrong-secret", "provider": "test", "status": "paid"},
            content_type="application/json",
            **wrong,
        )
        self.assertEqual(denied.status_code, 403)

        oversized = self.client.post(
            self.url,
            {"event_id": "x" * 257, "provider": "test", "status": "paid"},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertEqual(oversized.json()["error"]["code"], "event_id_too_long")

    @override_settings(PAYMENT_WEBHOOK_SHARED_SECRET="test-webhook-secret")
    def test_webhook_is_idempotent_and_records_one_audit_event(self):
        payload = {"event_id": "evt-123", "provider": "momo", "status": "paid"}
        first = self.client.post(
            self.url, payload, content_type="application/json", **self.headers
        )
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["replay"])

        replay = self.client.post(
            self.url, payload, content_type="application/json", **self.headers
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replay"])

        events = AuditEvent.objects.filter(
            tenant=self.tenant,
            action="integrations.payment_webhook_received",
            entity_id="evt-123",
        )
        self.assertEqual(events.count(), 1)

    @override_settings(PAYMENT_WEBHOOK_SHARED_SECRET="test-webhook-secret")
    def test_failed_audit_write_releases_idempotency_key_for_provider_retry(self):
        payload = {"event_id": "evt-retry-audit", "provider": "momo", "status": "paid"}
        with patch(
            "apps.api.payment_webhook_views.log_audit",
            side_effect=RuntimeError("audit unavailable"),
        ):
            failed = self.client.post(
                self.url, payload, content_type="application/json", **self.headers
            )
        self.assertEqual(failed.status_code, 500)
        failed_body = failed.json()
        self.assertEqual(failed_body["error"]["code"], "server_error")
        self.assertNotIn("audit unavailable", str(failed_body))

        retry = self.client.post(
            self.url, payload, content_type="application/json", **self.headers
        )
        self.assertEqual(retry.status_code, 200)
        self.assertFalse(retry.json()["replay"])
        self.assertEqual(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action="integrations.payment_webhook_received",
                entity_id="evt-retry-audit",
            ).count(),
            1,
        )

    def test_webhook_uses_constant_time_secret_comparison(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "payment_webhook_views.py"
        ).read_text(encoding="utf-8")
        self.assertIn("constant_time_compare", source)
        self.assertIn("hashlib.sha256", source)
        self.assertNotIn('request.headers.get("X-Webhook-Secret") != secret.strip()', source)
