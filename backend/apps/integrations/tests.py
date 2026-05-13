from __future__ import annotations

import base64
from decimal import Decimal
import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.finance.models import FinanceCategoryKind, FinancePostingSource
from apps.finance.services import post_cashbook_for_source
from apps.tenants.models import Tenant, TenantSettings

from .efris import EFRIS_PROVIDER_KEY
from .models import EfrisSubmission, EfrisSubmissionStatus, IntegrationLink
from .tasks import process_efris_submission_queue


class _FakeHttpResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self._status_code = status_code
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self) -> int:
        return self._status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class EfrisQueueTests(TestCase):
    def setUp(self) -> None:
        self.tenant = Tenant.objects.create(name="EFRIS Tenant", slug="efris-tenant")
        self.tenant_settings, _ = TenantSettings.objects.get_or_create(tenant=self.tenant)

    @override_settings(EFRIS_INTEGRATION_ENABLED=False)
    def test_global_efris_off_skips_queue_even_if_tenant_enabled(self) -> None:
        self.tenant_settings.efris_enabled = True
        self.tenant_settings.save(update_fields=["efris_enabled", "updated_at"])
        post_cashbook_for_source(
            tenant_id=self.tenant.id,
            source_type=FinancePostingSource.POS_PAYMENT,
            source_id="evt-1",
            kind=FinanceCategoryKind.INCOME,
            amount=Decimal("10.00"),
            reference="BILL-1",
            note="test",
        )
        self.assertEqual(EfrisSubmission.objects.count(), 0)

    @override_settings(EFRIS_INTEGRATION_ENABLED=True)
    def test_tenant_efris_off_skips_queue(self) -> None:
        self.tenant_settings.efris_enabled = False
        self.tenant_settings.save(update_fields=["efris_enabled", "updated_at"])
        post_cashbook_for_source(
            tenant_id=self.tenant.id,
            source_type=FinancePostingSource.POS_PAYMENT,
            source_id="evt-2",
            kind=FinanceCategoryKind.INCOME,
            amount=Decimal("12.00"),
            reference="BILL-2",
            note="test",
        )
        self.assertEqual(EfrisSubmission.objects.count(), 0)

    @override_settings(EFRIS_INTEGRATION_ENABLED=True)
    @patch("apps.integrations.efris.urlopen")
    def test_enabled_tenant_submits_queue_with_http_adapter(self, mocked_urlopen) -> None:
        self.tenant_settings.efris_enabled = True
        self.tenant_settings.save(update_fields=["efris_enabled", "updated_at"])
        IntegrationLink.objects.create(
            tenant=self.tenant,
            provider_key=EFRIS_PROVIDER_KEY,
            is_enabled=True,
            settings={
                "submit_endpoint": "https://efris.example/api/submit",
                "tin": "1234567890",
                "branch_id": "001",
                "device_no": "DVC-1",
                "access_token": "token-1",
                "signing_mode": "hmac_sha256",
                "api_secret": "secret",
                "encryption_mode": "none",
            },
        )
        mocked_urlopen.return_value = _FakeHttpResponse(
            200, {"status": "success", "data": {"invoiceNo": "EFRIS-OK-1"}}
        )
        post_cashbook_for_source(
            tenant_id=self.tenant.id,
            source_type=FinancePostingSource.POS_PAYMENT,
            source_id="evt-3",
            kind=FinanceCategoryKind.INCOME,
            amount=Decimal("20.00"),
            reference="BILL-3",
            note="test",
        )
        submission = EfrisSubmission.objects.get()
        self.assertEqual(submission.status, EfrisSubmissionStatus.PENDING)
        processed = process_efris_submission_queue()
        self.assertEqual(processed, 1)
        submission.refresh_from_db()
        self.assertEqual(submission.status, EfrisSubmissionStatus.SUBMITTED)
        self.assertEqual(submission.provider_reference, "EFRIS-OK-1")

    @override_settings(EFRIS_INTEGRATION_ENABLED=True)
    @patch("apps.integrations.efris.urlopen")
    def test_failed_submission_is_marked_failed_and_retry_scheduled(self, mocked_urlopen) -> None:
        self.tenant_settings.efris_enabled = True
        self.tenant_settings.save(update_fields=["efris_enabled", "updated_at"])
        IntegrationLink.objects.create(
            tenant=self.tenant,
            provider_key=EFRIS_PROVIDER_KEY,
            is_enabled=True,
            settings={
                "submit_endpoint": "https://efris.example/api/submit",
                "tin": "1234567890",
                "branch_id": "001",
                "device_no": "DVC-2",
                "access_token": "token-2",
            },
        )
        mocked_urlopen.return_value = _FakeHttpResponse(
            200, {"status": "error", "message": "Invalid fiscal data"}
        )
        post_cashbook_for_source(
            tenant_id=self.tenant.id,
            source_type=FinancePostingSource.POS_PAYMENT,
            source_id="evt-4",
            kind=FinanceCategoryKind.INCOME,
            amount=Decimal("15.00"),
            reference="BILL-4",
            note="test",
        )
        submission = EfrisSubmission.objects.get()
        process_efris_submission_queue()
        submission.refresh_from_db()
        self.assertEqual(submission.status, EfrisSubmissionStatus.FAILED)
        self.assertGreaterEqual(submission.attempts, 1)
        self.assertIsNotNone(submission.next_retry_at)

    @override_settings(EFRIS_INTEGRATION_ENABLED=True)
    @patch("apps.integrations.efris.urlopen")
    def test_encryption_and_signature_hooks_shape_request_payload(self, mocked_urlopen) -> None:
        self.tenant_settings.efris_enabled = True
        self.tenant_settings.save(update_fields=["efris_enabled", "updated_at"])
        IntegrationLink.objects.create(
            tenant=self.tenant,
            provider_key=EFRIS_PROVIDER_KEY,
            is_enabled=True,
            settings={
                "submit_endpoint": "https://efris.example/api/submit",
                "tin": "1234567890",
                "branch_id": "001",
                "device_no": "DVC-3",
                "access_token": "token-3",
                "signing_mode": "hmac_sha256",
                "api_secret": "signed-secret",
                "encryption_mode": "base64",
            },
        )
        captured: dict = {}

        def _capture(request, timeout=0):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["data"] = json.loads(request.data.decode("utf-8"))
            return _FakeHttpResponse(200, {"success": True, "reference": "REF-77"})

        mocked_urlopen.side_effect = _capture
        post_cashbook_for_source(
            tenant_id=self.tenant.id,
            source_type=FinancePostingSource.POS_PAYMENT,
            source_id="evt-5",
            kind=FinanceCategoryKind.INCOME,
            amount=Decimal("21.00"),
            reference="BILL-5",
            note="test",
        )
        process_efris_submission_queue()
        self.assertEqual(captured["url"], "https://efris.example/api/submit")
        self.assertIn("Authorization", captured["headers"])
        self.assertIn("signature", captured["data"])
        self.assertIn("data", captured["data"])
        decoded = base64.b64decode(captured["data"]["data"].encode("utf-8")).decode("utf-8")
        self.assertIn('"reference":"BILL-5"', decoded)
