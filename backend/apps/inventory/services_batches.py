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


def consume_fefo_batches(*, tenant, outlet, menu_item, quantity, as_of=None):
    """Atomically consume eligible batches, without changing the aggregate stock ledger.

    Callers integrating this with StockBalance must lock/update both ledgers in
    one outer transaction. Until then this operation is batch-ledger-only.
    """
    from django.db import transaction
    from django.db.models import F
    from .fefo import InsufficientBatchStock
    with transaction.atomic():
        if outlet.site.tenant_id != tenant.pk or menu_item.tenant_id != tenant.pk:
            raise ValueError("Batch request must remain within one tenant")
        batches = list(InventoryBatch.objects.select_for_update().filter(
            tenant=tenant, outlet=outlet, menu_item=menu_item,
            quarantined=False, remaining_quantity__gt=0,
        ).order_by("expiry_date", "id"))
        plan = plan_fefo_allocation(
            ({"id": b.pk, "quantity": b.remaining_quantity, "expiry_date": b.expiry_date}
             for b in batches), quantity, as_of=as_of or date.today(),
        )
        by_id = {b.pk: b for b in batches}
        for batch_id, used in plan:
            batch = by_id[batch_id]
            if used > batch.remaining_quantity:
                raise InsufficientBatchStock("Concurrent allocation exceeded batch availability")
            InventoryBatch.objects.filter(pk=batch.pk, remaining_quantity__gte=used).update(
                remaining_quantity=F("remaining_quantity") - used,
            )
        return plan


def receive_tracked_batch(*, tenant, outlet, menu_item, batch_code, quantity,
                          received_at, expiry_date=None, user=None, purchase_order=None):
    """Receive a named batch and post the same quantity into aggregate inventory.

    Both writes use one transaction. Existing unlabeled legacy stock stays
    outside batch tracking until explicitly reconciled. Duplicate codes fail
    without adding stock a second time.
    """
    from django.db import IntegrityError, transaction
    from rest_framework.exceptions import ValidationError
    from .models import StockReason
    from .services import apply_manual_stock_change

    if outlet.site.tenant_id != tenant.pk or menu_item.tenant_id != tenant.pk:
        raise ValidationError({"batch": "Outlet and product must belong to the tenant."})
    if purchase_order is not None and (
        purchase_order.tenant_id != tenant.pk or purchase_order.outlet_id != outlet.pk
    ):
        raise ValidationError({"purchase_order": "Purchase order scope mismatch."})
    try:
        amount = Decimal(str(quantity))
    except (ValueError, TypeError, ArithmeticError):
        raise ValidationError({"quantity": "Enter a valid positive quantity."})
    if not amount.is_finite() or amount <= 0:
        raise ValidationError({"quantity": "Enter a positive finite quantity."})
    if not batch_code or len(batch_code.strip()) > 128:
        raise ValidationError({"batch_code": "A batch code of at most 128 characters is required."})
    if expiry_date is not None and expiry_date < received_at:
        raise ValidationError({"expiry_date": "Expiry date cannot precede receipt."})
    with transaction.atomic():
        # This lock protects the normal stock balance while the unique
        # batch constraint rejects duplicate receipts.
        if InventoryBatch.objects.filter(
            outlet=outlet, menu_item=menu_item, batch_code=batch_code.strip()
        ).exists():
            raise ValidationError({"batch_code": "This batch code already exists at this outlet."})
        batch = InventoryBatch.objects.create(
            tenant=tenant, outlet=outlet, menu_item=menu_item,
            batch_code=batch_code.strip(), received_at=received_at,
            expiry_date=expiry_date, received_quantity=amount,
            remaining_quantity=amount,
        )
        movement = apply_manual_stock_change(
            tenant_id=tenant.pk, outlet=outlet, menu_item=menu_item,
            quantity_change=amount, reason=StockReason.RECEIVE,
            user=user, note=f"Batch {batch.batch_code}",
            purchase_order=purchase_order,
        )
    return batch, movement
