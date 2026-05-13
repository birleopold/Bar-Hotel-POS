from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import EfrisSubmission, EfrisSubmissionStatus
from .services import process_efris_submission


@shared_task
def process_efris_submission_queue() -> int:
    """
    Poll and process queued EFRIS submissions.
    Safe to run frequently; no-op when integration is globally disabled.
    """
    if not getattr(settings, "EFRIS_INTEGRATION_ENABLED", False):
        return 0
    limit = int(getattr(settings, "EFRIS_QUEUE_BATCH_SIZE", 50))
    now = timezone.now()
    ids = list(
        EfrisSubmission.objects.filter(
            status__in=[EfrisSubmissionStatus.PENDING, EfrisSubmissionStatus.FAILED]
        ).filter(
            Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
        )
        .order_by("created_at")
        .values_list("id", flat=True)[:limit]
    )
    processed = 0
    for sid in ids:
        if process_efris_submission(sid) is not None:
            processed += 1
    return processed
