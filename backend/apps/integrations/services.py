from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.finance.models import CashbookEntry
from apps.tenants.models import TenantSettings

from .efris import get_efris_adapter
from .models import EfrisSubmission, EfrisSubmissionStatus


def _build_cashbook_payload(entry: CashbookEntry) -> dict:
    category = entry.category
    return {
        "cashbook_entry_id": str(entry.id),
        "tenant_id": str(entry.tenant_id),
        "site_id": str(entry.site_id) if entry.site_id else None,
        "category_id": str(category.id),
        "category_name": category.name,
        "category_kind": category.kind,
        "amount": str(entry.amount),
        "transaction_date": entry.transaction_date.isoformat(),
        "reference": entry.reference,
        "note": entry.note,
        "created_at": entry.created_at.isoformat(),
    }


def _tenant_efris_enabled(tenant_id) -> bool:
    if not getattr(settings, "EFRIS_INTEGRATION_ENABLED", False):
        return False
    ts = TenantSettings.objects.filter(tenant_id=tenant_id).only("efris_enabled").first()
    return bool(ts and ts.efris_enabled)


@transaction.atomic
def enqueue_efris_submission_for_cashbook_entry(entry: CashbookEntry) -> tuple[EfrisSubmission | None, bool]:
    """
    Enqueue outbox row only when EFRIS is globally + tenant enabled.
    Returns (submission, replay) where replay=True means existing queue row was reused.
    """
    if not _tenant_efris_enabled(entry.tenant_id):
        return None, False

    existing = (
        EfrisSubmission.objects.select_for_update()
        .filter(tenant_id=entry.tenant_id, cashbook_entry_id=entry.id)
        .first()
    )
    if existing is not None:
        return existing, True

    submission = EfrisSubmission.objects.create(
        tenant_id=entry.tenant_id,
        cashbook_entry=entry,
        payload=_build_cashbook_payload(entry),
        status=EfrisSubmissionStatus.PENDING,
    )
    return submission, False


@transaction.atomic
def process_efris_submission(submission_id) -> EfrisSubmission | None:
    """
    Run one adapter attempt. On failure, ``last_error`` holds a short, human-readable
    message (HTTP/validation text from ``submit_receipt``); ops should use the staff
    EFRIS page queue and Django admin for inspection—this is not a machine error code enum yet.
    """
    submission = (
        EfrisSubmission.objects.select_for_update()
        .select_related("cashbook_entry")
        .filter(id=submission_id)
        .first()
    )
    if submission is None:
        return None
    if submission.status == EfrisSubmissionStatus.SUBMITTED:
        return submission
    if not _tenant_efris_enabled(submission.tenant_id):
        # Preserve queue but avoid processing when feature is toggled off.
        return submission

    submission.status = EfrisSubmissionStatus.PROCESSING
    submission.attempts += 1
    submission.last_error = ""
    submission.save(update_fields=["status", "attempts", "last_error", "updated_at"])

    adapter = get_efris_adapter()
    result = adapter.submit_receipt(tenant_id=submission.tenant_id, payload=submission.payload or {})
    if result.success:
        submission.status = EfrisSubmissionStatus.SUBMITTED
        submission.provider_reference = (result.provider_reference or "")[:128]
        submission.submitted_at = timezone.now()
        submission.next_retry_at = None
        submission.last_error = ""
        submission.save(
            update_fields=[
                "status",
                "provider_reference",
                "submitted_at",
                "next_retry_at",
                "last_error",
                "updated_at",
            ]
        )
        return submission

    backoff_seconds = getattr(settings, "EFRIS_RETRY_BASE_SECONDS", 300) * max(1, submission.attempts)
    submission.status = EfrisSubmissionStatus.FAILED
    submission.last_error = (result.error_message or "Unknown EFRIS submission error.")[:2000]
    submission.next_retry_at = timezone.now() + timedelta(seconds=backoff_seconds)
    submission.save(update_fields=["status", "last_error", "next_retry_at", "updated_at"])
    return submission


def pending_efris_submission_ids(*, limit: int) -> list:
    now = timezone.now()
    return list(
        EfrisSubmission.objects.filter(
            status__in=[EfrisSubmissionStatus.PENDING, EfrisSubmissionStatus.FAILED]
        ).filter(
            Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
        )
        .order_by("created_at")
        .values_list("id", flat=True)[:limit]
    )
