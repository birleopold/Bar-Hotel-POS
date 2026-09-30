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
    discount_threshold = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    stock_adjustment_threshold = models.DecimalField(max_digits=14, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    pin_failure_threshold = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    offline_age_hours = models.PositiveSmallIntegerField(default=24, validators=[MinValueValidator(1), MaxValueValidator(168)])
    lookback_days = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(365)])


    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(discount_threshold__gte=0, stock_adjustment_threshold__gte=0, pin_failure_threshold__gte=1, pin_failure_threshold__lte=5, offline_age_hours__gte=1, offline_age_hours__lte=168), name="valid_exception_extra_policy"),
            models.CheckConstraint(condition=models.Q(cash_variance_threshold__gte=0, refund_threshold__gte=0, lookback_days__gte=1, lookback_days__lte=365), name="valid_exception_policy"),
        ]


class ExceptionReview(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="exception_reviews")
    kind = models.CharField(max_length=32)
    entity_id = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=[("open", "Open"), ("reviewed", "Reviewed"), ("follow_up", "Follow up"), ("resolved", "Resolved review")], default="open")
    note = models.CharField(max_length=1000)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    reviewed_at = models.DateTimeField(auto_now=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_exception_reviews")
    due_date = models.DateField(null=True, blank=True)
    scope_outlet = models.ForeignKey("tenants.Outlet", on_delete=models.PROTECT, null=True, blank=True)
    scope_site = models.ForeignKey("tenants.Site", on_delete=models.PROTECT, null=True, blank=True)
    source_url = models.CharField(max_length=255, blank=True)

    @property
    def kind_label(self):
        return "EFRIS failure" if self.kind == "efris_failure" else self.kind.replace("_", " ").capitalize()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "kind", "entity_id", "fingerprint"], name="unique_exception_review_version")]
