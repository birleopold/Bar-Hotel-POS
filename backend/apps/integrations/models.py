import uuid

from django.db import models

from apps.common.models import TimeStampedModel


class IntegrationLink(TimeStampedModel):
    """
    Registry row per tenant + provider (marketplace / integrations hub).
    Store only non-secret preferences here; put secrets in env or a vault.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="integration_links",
    )
    provider_key = models.CharField(
        max_length=64,
        help_text="Stable key e.g. stripe_connect, mailchimp, sms_gateway.",
    )
    label = models.CharField(max_length=128, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    is_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ["tenant", "provider_key"]
        unique_together = [["tenant", "provider_key"]]

    def __str__(self) -> str:
        return f"{self.tenant.slug}:{self.provider_key}"


class EfrisSubmissionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    SUBMITTED = "submitted", "Submitted"
    FAILED = "failed", "Failed"


class EfrisSubmission(TimeStampedModel):
    """
    Outbox queue for optional tenant-level EFRIS submission.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="efris_submissions",
    )
    cashbook_entry = models.OneToOneField(
        "finance.CashbookEntry",
        on_delete=models.CASCADE,
        related_name="efris_submission",
    )
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=EfrisSubmissionStatus.choices,
        default=EfrisSubmissionStatus.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    provider_reference = models.CharField(max_length=128, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"EFRIS {self.tenant.slug} {self.status}"
