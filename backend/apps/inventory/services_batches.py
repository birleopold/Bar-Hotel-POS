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
    from django.db import transaction
    from django.utils import timezone
    from rest_framework.exceptions import ValidationError
    from .models import StockBalance, StockReason
    from .services import apply_manual_stock_change

    if outlet.site.tenant_id != tenant.pk or menu_item.tenant_id != tenant.pk:
        raise ValidationError({"batch": "Outlet and product must belong to the tenant."})
    if not menu_item.track_inventory:
        raise ValidationError({"menu_item": "Enable inventory tracking before receiving a batch."})
    today = timezone.localdate()
    if not isinstance(received_at, date) or received_at > today:
        raise ValidationError({"received_at": "Use an actual receipt date, not a future date."})
    if purchase_order is not None and (
        purchase_order.tenant_id != tenant.pk or purchase_order.outlet_id != outlet.pk
    ):
        raise ValidationError({"purchase_order": "Purchase order scope mismatch."})
    try:
        amount = Decimal(str(quantity))
    except (ValueError, TypeError, ArithmeticError):
        raise ValidationError({"quantity": "Enter a valid positive quantity."})
    if (not amount.is_finite() or amount <= 0
            or amount != amount.quantize(Decimal("0.001"))):
        raise ValidationError({"quantity": "Enter a positive quantity with up to three decimal places."})
    if not batch_code or len(batch_code.strip()) > 128:
        raise ValidationError({"batch_code": "A batch code of at most 128 characters is required."})
    if expiry_date is not None and expiry_date < received_at:
        raise ValidationError({"expiry_date": "Expiry date cannot precede receipt."})
    with transaction.atomic():
        # Serialize intake with POS/stock outflow; the existing unique batch
        # key also prevents two concurrent receipts using the same lot code.
        StockBalance.objects.select_for_update().get_or_create(
            tenant_id=tenant.pk, outlet=outlet, menu_item=menu_item,
            defaults={"quantity": Decimal("0")},
        )
        if InventoryBatch.objects.filter(
            outlet=outlet, menu_item=menu_item, batch_code=batch_code.strip()
        ).exists():
            raise ValidationError({"batch_code": "This batch code already exists at this outlet."})
        batch = InventoryBatch.objects.create(
            tenant=tenant, outlet=outlet, menu_item=menu_item,
            batch_code=batch_code.strip(), received_at=received_at,
            expiry_date=expiry_date, received_quantity=amount,
            remaining_quantity=amount,
            quarantined=bool(expiry_date is not None and expiry_date < today),
        )
        movement = apply_manual_stock_change(
            tenant_id=tenant.pk, outlet=outlet, menu_item=menu_item,
            quantity_change=amount, reason=StockReason.RECEIVE,
            user=user, note=f"Batch {batch.batch_code}",
            purchase_order=purchase_order,
        )
        # Show receipts as well as outflows in each batch's traceability screen.
        record_batch_allocations(
            tenant_id=tenant.pk, movement=movement,
            allocations=[(batch.pk, amount)],
        )
        from apps.audit.services import log_audit
        log_audit(
            tenant_id=tenant.pk, user_id=user.pk if user else None,
            action="inventory.batch_received",
            entity_type="inventory_batch", entity_id=str(batch.pk),
            payload={
                "outlet_id": str(outlet.pk),
                "menu_item_id": str(menu_item.pk),
                "batch_code": batch.batch_code,
                "quantity": str(amount),
                "expiry_date": expiry_date.isoformat() if expiry_date else None,
                "quarantined": batch.quarantined,
                "movement_id": str(movement.pk),
                "purchase_order_id": str(purchase_order.pk) if purchase_order else None,
            },
        )
    return batch, movement



def consume_for_outflow_if_batched(*, tenant_id, outlet_id, menu_item_id, quantity):
    """Use FEFO alongside an existing negative aggregate stock posting.

    Items with no batch history retain the legacy stock process. Once any batch
    is received for an item/outlet, every further outflow needs eligible batch
    quantity; unknown, held or expired quantities cannot quietly be sold.
    Call from the SAME transaction that holds the StockBalance row lock.
    """
    from rest_framework.exceptions import ValidationError
    from .fefo import InsufficientBatchStock

    if not InventoryBatch.objects.filter(
        tenant_id=tenant_id, outlet_id=outlet_id, menu_item_id=menu_item_id,
    ).exists():
        return []
    from apps.tenants.models import Tenant, Outlet
    from apps.catalog.models import MenuItem
    try:
        return consume_fefo_batches(
            tenant=Tenant.objects.get(pk=tenant_id),
            outlet=Outlet.objects.select_related("site").get(pk=outlet_id),
            menu_item=MenuItem.objects.get(pk=menu_item_id),
            quantity=quantity,
        )
    except InsufficientBatchStock as exc:
        raise ValidationError({
            "stock": "Not enough usable batches. Check expired or held stock and reconcile older stock before proceeding."
        }) from exc


def change_batch_hold(*, tenant_id, batch_id, allowed_outlet_ids, quarantined, user, note=""):
    """Hold or release batch stock without changing counted quantities."""
    from django.db import transaction
    from django.shortcuts import get_object_or_404
    from apps.audit.services import log_audit
    from rest_framework.exceptions import ValidationError
    if not allowed_outlet_ids:
        raise ValidationError({"batch": "No permitted stock section."})
    with transaction.atomic():
        batch = get_object_or_404(
            InventoryBatch.objects.select_for_update(),
            pk=batch_id, tenant_id=tenant_id, outlet_id__in=allowed_outlet_ids,
        )
        old = batch.quarantined
        if not quarantined and batch.expiry_date is not None and batch.expiry_date < date.today():
            raise ValidationError({"batch": "Expired batches cannot be released for sale. Record a write-off or return instead."})
        if old != quarantined:
            batch.quarantined = quarantined
            batch.save(update_fields=["quarantined", "updated_at"])
            log_audit(
                tenant_id=tenant_id, user_id=user.pk if user else None,
                action="inventory.batch_hold_changed", entity_type="inventory_batch",
                entity_id=str(batch.pk),
                payload={"outlet_id": str(batch.outlet_id),
                         "before": old, "after": quarantined, "reason": note[:512]},
            )
        return batch


def waste_batch_stock(*, tenant_id, batch_id, allowed_outlet_ids, quantity, user, reason):
    """Post an explicitly selected expired/damaged batch and ledger write-off."""
    from django.db import transaction
    from django.shortcuts import get_object_or_404
    from apps.audit.services import log_audit
    from .models import StockBalance, StockMovement, StockReason
    from rest_framework.exceptions import ValidationError

    if not allowed_outlet_ids:
        raise ValidationError({"batch": "No permitted stock section."})
    try:
        amount = Decimal(str(quantity))
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError({"quantity": "Enter a valid quantity."})
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.001")):
        raise ValidationError({"quantity": "Enter a positive quantity with up to three decimal places."})
    note = (reason or "").strip()
    if not note or len(note) > 450:
        raise ValidationError({"reason": "Explain the write-off (up to 450 characters)."})
    with transaction.atomic():
        batch = get_object_or_404(
            InventoryBatch.objects.select_for_update(),
            pk=batch_id, tenant_id=tenant_id, outlet_id__in=allowed_outlet_ids,
        )
        balance = get_object_or_404(
            StockBalance.objects.select_for_update(),
            tenant_id=tenant_id, outlet_id=batch.outlet_id, menu_item_id=batch.menu_item_id,
        )
        if amount > batch.remaining_quantity or amount > balance.quantity:
            raise ValidationError({"quantity": "Quantity exceeds the batch or available stock balance."})
        batch.remaining_quantity -= amount
        batch.save(update_fields=["remaining_quantity", "updated_at"])
        balance.quantity -= amount
        balance.save(update_fields=["quantity", "updated_at"])
        movement = StockMovement.objects.create(
            tenant_id=tenant_id, outlet_id=batch.outlet_id, menu_item_id=batch.menu_item_id,
            quantity_change=-amount, reason=StockReason.WASTE,
            created_by=user, note=f"Batch {batch.batch_code}: {note}"[:512],
        )
        record_batch_allocations(tenant_id=tenant_id, movement=movement, allocations=[(batch.pk, amount)])
        log_audit(
            tenant_id=tenant_id, user_id=user.pk if user else None,
            action="inventory.batch_written_off", entity_type="inventory_batch",
            entity_id=str(batch.pk), payload={
                "outlet_id": str(batch.outlet_id), "menu_item_id": str(batch.menu_item_id),
                "amount": str(amount), "reason": note, "movement_id": str(movement.pk),
            },
        )
        return movement



def label_existing_stock_batch(*, tenant_id, outlet, menu_item, batch_code,
                               quantity, received_at, expiry_date, user):
    """Explicitly assign already-counted stock to a batch without re-receiving it.

    The aggregate stock balance must not increase; the transaction caps the
    allocation at quantity not already assigned to batches. This is the safe
    manual migration path for earlier unlabeled stock.
    """
    from django.db import transaction
    from django.db.models import Sum
    from rest_framework.exceptions import ValidationError
    from apps.audit.services import log_audit
    from .models import StockBalance

    if outlet.site.tenant_id != tenant_id or menu_item.tenant_id != tenant_id:
        raise ValidationError({"stock": "Section and product must belong to the active business."})
    if not menu_item.track_inventory:
        raise ValidationError({"menu_item": "Select an inventory-tracked product."})
    try:
        amount = Decimal(str(quantity))
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError({"quantity": "Enter a valid quantity."})
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.001")):
        raise ValidationError({"quantity": "Enter a positive quantity with at most three decimal places."})
    code = (batch_code or "").strip()
    if not code or len(code) > 128:
        raise ValidationError({"batch_code": "Enter a batch code up to 128 characters."})
    if expiry_date is not None and expiry_date < received_at:
        raise ValidationError({"expiry_date": "Expiry cannot be before the receipt date."})
    with transaction.atomic():
        balance = StockBalance.objects.select_for_update().filter(
            tenant_id=tenant_id, outlet=outlet, menu_item=menu_item,
        ).first()
        if balance is None:
            raise ValidationError({"quantity": "There is no existing stock to label."})
        previous = InventoryBatch.objects.select_for_update().filter(
            tenant_id=tenant_id, outlet=outlet, menu_item=menu_item,
        )
        already_assigned = previous.aggregate(total=Sum("remaining_quantity"))["total"] or Decimal("0")
        if amount > balance.quantity - already_assigned:
            raise ValidationError({"quantity": "Quantity exceeds stock that is not yet assigned to a batch."})
        if previous.filter(batch_code=code).exists():
            raise ValidationError({"batch_code": "This batch code already exists for the product in this section."})
        batch = InventoryBatch.objects.create(
            tenant_id=tenant_id, outlet=outlet, menu_item=menu_item,
            batch_code=code, received_at=received_at, expiry_date=expiry_date,
            received_quantity=amount, remaining_quantity=amount,
            quarantined=bool(expiry_date is not None and expiry_date < date.today()),
        )
        log_audit(
            tenant_id=tenant_id, user_id=user.pk if user else None,
            action="inventory.legacy_stock_labeled",
            entity_type="inventory_batch", entity_id=str(batch.pk),
            payload={
                "outlet_id": str(outlet.pk), "menu_item_id": str(menu_item.pk),
                "quantity": str(amount), "balance_unchanged": True,
            },
        )
        return batch


def record_batch_allocations(*, tenant_id, movement, allocations):
    """Attach the exact batch quantities used by a stock ledger movement."""
    from .models import StockBatchAllocation
    if movement.tenant_id != tenant_id:
        raise ValueError("Stock movement tenant does not match")
    for batch_id, quantity in allocations:
        batch = InventoryBatch.objects.get(pk=batch_id)
        if (batch.tenant_id != tenant_id or batch.outlet_id != movement.outlet_id
                or batch.menu_item_id != movement.menu_item_id or quantity <= 0):
            raise ValueError("Stock movement and batch scope mismatch")
        StockBatchAllocation.objects.create(
            tenant_id=tenant_id, stock_movement=movement,
            batch=batch, quantity=quantity,
        )



def hold_matching_lot(*, tenant_id, batch_id, allowed_outlet_ids, user, reason):
    """Hold matching product/lot stock at every accessible outlet.

    A recall hold is not a refund, write-off, notification, or a claim that all
    already-sold goods have been recovered.
    """
    from django.db import transaction
    from rest_framework.exceptions import ValidationError
    from django.shortcuts import get_object_or_404
    from apps.audit.services import log_audit

    note = (reason or "").strip()
    if not note or len(note) > 450:
        raise ValidationError({"reason": "State why this lot is being held (up to 450 characters)."})
    if not allowed_outlet_ids:
        raise ValidationError({"batch": "No permitted stock section."})
    with transaction.atomic():
        original = get_object_or_404(
            InventoryBatch.objects.select_for_update(),
            pk=batch_id, tenant_id=tenant_id, outlet_id__in=allowed_outlet_ids,
        )
        matched = list(InventoryBatch.objects.select_for_update().filter(
            tenant_id=tenant_id, outlet_id__in=allowed_outlet_ids,
            menu_item_id=original.menu_item_id, batch_code=original.batch_code,
        ).order_by("pk"))
        for batch in matched:
            if not batch.quarantined:
                batch.quarantined = True
                batch.save(update_fields=["quarantined", "updated_at"])
        log_audit(
            tenant_id=tenant_id, user_id=user.pk if user else None,
            action="inventory.lot_recall_hold", entity_type="inventory_batch",
            entity_id=str(original.pk),
            payload={
                "menu_item_id": str(original.menu_item_id),
                "batch_code": original.batch_code,
                "affected_batch_ids": [str(batch.pk) for batch in matched],
                "reason": note,
            },
        )
        return len(matched)
