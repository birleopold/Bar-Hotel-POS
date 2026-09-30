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
