"""Safe read-only FEFO availability report using persisted batches."""
from datetime import date
from decimal import Decimal

from .batches import InventoryBatch
from .fefo import plan_fefo_allocation


def available_fefo_plan(*, tenant, outlet, menu_item, quantity, as_of=None):
    if outlet.site.tenant_id != tenant.pk or menu_item.tenant_id != tenant.pk:
        raise ValueError("Batch request must remain within one tenant")
    rows = InventoryBatch.objects.filter(
        tenant=tenant, outlet=outlet, menu_item=menu_item,
        quarantined=False, remaining_quantity__gt=Decimal("0"),
    ).values("id", "remaining_quantity", "expiry_date")
    return plan_fefo_allocation(
        ({"id": row["id"], "quantity": row["remaining_quantity"],
          "expiry_date": row["expiry_date"]} for row in rows),
        quantity, as_of=as_of or date.today(),
    )
