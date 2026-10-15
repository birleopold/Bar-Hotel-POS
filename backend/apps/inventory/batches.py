"""Persisted batch receipts and FEFO allocation records.

Separate from StockBalance until reconciliation and full migration are complete.
"""
import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q
from apps.common.models import TimeStampedModel


class InventoryBatch(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="inventory_batches")
    outlet = models.ForeignKey("tenants.Outlet", on_delete=models.CASCADE, related_name="inventory_batches")
    menu_item = models.ForeignKey("catalog.MenuItem", on_delete=models.PROTECT, related_name="inventory_batches")
    batch_code = models.CharField(max_length=128)
    received_at = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    received_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    remaining_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    quarantined = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["outlet", "menu_item", "batch_code"], name="uniq_inventory_batch_per_item_outlet"),
            models.CheckConstraint(condition=Q(received_quantity__gte=0), name="inventory_batch_received_nonnegative"),
            models.CheckConstraint(condition=Q(remaining_quantity__gte=0), name="inventory_batch_remaining_nonnegative"),
        ]

    def __str__(self):
        return self.batch_code
