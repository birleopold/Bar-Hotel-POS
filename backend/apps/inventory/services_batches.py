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


def batch_expiry_alerts(*, tenant, outlet, as_of=None, within_days=30):
    """Read-only expiry/quarantine queue; no automated disposal."""
    from datetime import timedelta
    if not isinstance(within_days, int) or not 0 <= within_days <= 365:
        raise ValueError("within_days must be between 0 and 365")
    if outlet.site.tenant_id != tenant.pk:
        raise ValueError("outlet must belong to tenant")
    today = as_of or date.today()
    horizon = today + timedelta(days=within_days)
    result = []
    batches = InventoryBatch.objects.filter(
        tenant=tenant, outlet=outlet, remaining_quantity__gt=0,
    ).select_related("menu_item").order_by("expiry_date", "batch_code")
    for batch in batches:
        if batch.quarantined:
            status = "quarantined"
        elif batch.expiry_date is not None and batch.expiry_date < today:
            status = "expired"
        elif batch.expiry_date is not None and batch.expiry_date <= horizon:
            status = "expiring_soon"
        else:
            continue
        result.append({
            "batch_id": batch.pk,
            "batch_code": batch.batch_code,
            "item": batch.menu_item.name,
            "remaining_quantity": batch.remaining_quantity,
            "expiry_date": batch.expiry_date,
            "status": status,
        })
    return result
