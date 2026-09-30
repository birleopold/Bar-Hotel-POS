import uuid

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=64, db_index=True)
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}:{self.entity_id}"


class ExceptionPolicy(models.Model):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="exception_policy")
    cash_variance_threshold = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    refund_threshold = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    lookback_days = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(365)])


    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(cash_variance_threshold__gte=0, refund_threshold__gte=0, lookback_days__gte=1, lookback_days__lte=365), name="valid_exception_policy"),
        ]


class ExceptionReview(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="exception_reviews")
    kind = models.CharField(max_length=32)
    entity_id = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=[("open", "Open"), ("reviewed", "Reviewed")], default="open")
    note = models.CharField(max_length=1000)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    reviewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "kind", "entity_id", "fingerprint"], name="unique_exception_review_version")]
