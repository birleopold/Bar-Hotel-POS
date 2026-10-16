import uuid

from django.db import models

from apps.common.models import TimeStampedModel


class Customer(TimeStampedModel):
    """Shared identity; historical transaction names remain immutable snapshots."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    preferences = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    merged_into = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="merged_records")
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self):
        return self.name



class LoyaltyLedgerEntry(models.Model):
    """Immutable, tenant-scoped points movement with a unique source key."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="loyalty_entries")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="loyalty_entries")
    points = models.IntegerField()
    source_type = models.CharField(max_length=24, choices=[
        ("adjustment", "Manager adjustment"),
        ("sale", "Sale reward"),
        ("refund", "Refund reversal"),
        ("redemption", "Reward redemption"),
    ])
    source_key = models.CharField(max_length=128)
    reason = models.CharField(max_length=300)
    recorded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "source_type", "source_key"], name="uniq_loyalty_source"),
            models.CheckConstraint(condition=~models.Q(points=0), name="nonzero_loyalty_points"),
        ]
