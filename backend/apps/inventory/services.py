import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import Membership
from apps.audit.services import log_audit
from apps.pos.models import Order

from .models import (
    StockBalance,
    StockCountLine,
    StockCountSession,
    StockCountStatus,
    StockMovement,
    StockReason,
)

@transaction.atomic
def apply_manual_stock_change(
    *,
    tenant_id,
    outlet,
    menu_item,
    quantity_change: Decimal,
    reason: str,
    user,
    note: str = "",
    purchase_order=None,
) -> StockMovement:
    """Apply a non-sale movement and update ``StockBalance``."""
    if quantity_change == 0:
        raise ValidationError({"quantity_change": "Must be non-zero."})

    if reason in (StockReason.RECEIVE, StockReason.ADJUST_IN) and quantity_change < 0:
        raise ValidationError({"quantity_change": "Must be positive for receive / adjust-in."})
    if reason in (StockReason.ADJUST_OUT, StockReason.WASTE) and quantity_change > 0:
        raise ValidationError({"quantity_change": "Must be negative for adjust-out / waste."})

    bal, _ = StockBalance.objects.select_for_update().get_or_create(
        outlet=outlet,
        menu_item=menu_item,
        defaults={"tenant_id": tenant_id, "quantity": Decimal("0")},
    )
    new_qty = bal.quantity + quantity_change
    if new_qty < 0:
        raise ValidationError(
            {"quantity_change": f"Would make on-hand negative (currently {bal.quantity})."}
        )
    bal.quantity = new_qty
    bal.save(update_fields=["quantity", "updated_at"])

    movement = StockMovement.objects.create(
        tenant_id=tenant_id,
        outlet=outlet,
        menu_item=menu_item,
        quantity_change=quantity_change,
        reason=reason,
        created_by=user,
        note=note[:512],
        purchase_order=purchase_order,
    )
    payload = {
        "reason": reason,
        "menu_item_id": str(menu_item.id),
        "outlet_id": str(outlet.id),
        "quantity_change": str(quantity_change),
    }
    if purchase_order is not None:
        payload["purchase_order_id"] = str(purchase_order.id)
    log_audit(
        tenant_id=tenant_id,
        user_id=user.id if user else None,
        action="stock.movement",
        entity_type="stock_movement",
        entity_id=str(movement.id),
        payload=payload,
    )
    return movement


@transaction.atomic
def validate_and_consume_stock_for_paid_order(order: Order, user) -> None:
    """
    For lines whose menu item has ``track_inventory``, ensure sufficient quantity
    at the order outlet, then decrement and record SALE movements.
    When ``consume_recipe_on_sale`` is set, also consumes recipe ingredients (RECIPE movements).
    """
    from apps.catalog.models import MenuItem

    tenant_id = order.tenant_id
    outlet_id = order.outlet_id
    lines = list(
        order.lines.select_related("menu_item").filter(
            is_voided=False,
            menu_item__isnull=False,
            menu_item__track_inventory=True,
        )
    )
    item_need: dict = {}
    item_names: dict = {}
    for line in lines:
        item_need[line.menu_item_id] = item_need.get(line.menu_item_id, Decimal("0")) + line.quantity
        item_names[line.menu_item_id] = line.menu_item.name

    for item_id, need in sorted(item_need.items(), key=lambda row: str(row[0])):
        bal, _ = StockBalance.objects.select_for_update().get_or_create(
            outlet_id=outlet_id,
            menu_item_id=item_id,
            defaults={"tenant_id": tenant_id, "quantity": Decimal("0")},
        )
        if bal.quantity < need:
            raise ValidationError(
                {
                    "stock": (
                        f'Insufficient stock for "{item_names[item_id]}" '
                        f"(need {need}, have {bal.quantity})."
                    )
                }
            )

    for item_id, need in sorted(item_need.items(), key=lambda row: str(row[0])):
        bal = StockBalance.objects.select_for_update().get(
            outlet_id=outlet_id,
            menu_item_id=item_id,
        )
        bal.quantity -= need
        bal.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            tenant_id=tenant_id,
            outlet_id=outlet_id,
            menu_item_id=item_id,
            quantity_change=-need,
            reason=StockReason.SALE,
            order=order,
            created_by=user,
        )

    ingredient_need: dict = {}
    for line in (
        order.lines.filter(is_voided=False, menu_item__isnull=False)
        .select_related("menu_item")
        .prefetch_related("menu_item__recipe_lines__ingredient_item")
    ):
        mi = line.menu_item
        if not mi.consume_recipe_on_sale:
            continue
        for rl in mi.recipe_lines.all():
            ing = rl.ingredient_item
            if not ing.track_inventory:
                continue
            need = (line.quantity * rl.quantity_per_unit).quantize(Decimal("0.001"))
            ingredient_need[ing.id] = ingredient_need.get(ing.id, Decimal("0")) + need

    for ing_id, need in sorted(ingredient_need.items(), key=lambda x: str(x[0])):
        if need <= 0:
            continue
        bal, _ = StockBalance.objects.select_for_update().get_or_create(
            outlet_id=outlet_id,
            menu_item_id=ing_id,
            defaults={"tenant_id": tenant_id, "quantity": Decimal("0")},
        )
        if bal.quantity < need:
            ing = MenuItem.objects.get(pk=ing_id)
            raise ValidationError(
                {
                    "stock": (
                        f'Insufficient stock for recipe ingredient "{ing.name}" '
                        f"(need {need}, have {bal.quantity})."
                    )
                }
            )

    for ing_id, need in ingredient_need.items():
        if need <= 0:
            continue
        bal = StockBalance.objects.select_for_update().get(
            outlet_id=outlet_id,
            menu_item_id=ing_id,
        )
        bal.quantity -= need
        bal.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            tenant_id=tenant_id,
            outlet_id=outlet_id,
            menu_item_id=ing_id,
            quantity_change=-need,
            reason=StockReason.RECIPE,
            order=order,
            created_by=user,
        )


@transaction.atomic
def execute_stock_transfer(
    *,
    tenant_id,
    membership: Membership,
    from_outlet,
    to_outlet,
    menu_item,
    quantity: Decimal,
    user,
    note: str = "",
) -> tuple[uuid.UUID, StockMovement, StockMovement]:
    if quantity <= 0:
        raise ValidationError({"quantity": "Must be positive."})
    if from_outlet.id == to_outlet.id:
        raise ValidationError({"to_outlet": "Destination must differ from source."})
    if from_outlet.site.tenant_id != tenant_id or to_outlet.site.tenant_id != tenant_id:
        raise ValidationError("Outlets must belong to the current tenant.")
    if not outlet_belongs_to_membership(membership, from_outlet.id):
        raise ValidationError({"from_outlet": "You cannot transfer from this outlet."})
    if not outlet_belongs_to_membership(membership, to_outlet.id):
        raise ValidationError({"to_outlet": "You cannot transfer to this outlet."})
    if not menu_item.track_inventory:
        raise ValidationError({"menu_item": "Enable track_inventory on this item."})

    batch = uuid.uuid4()
    note_text = (note or "")[:500]

    bal_from, _ = StockBalance.objects.select_for_update().get_or_create(
        outlet=from_outlet,
        menu_item=menu_item,
        defaults={"tenant_id": tenant_id, "quantity": Decimal("0")},
    )
    if bal_from.quantity < quantity:
        raise ValidationError(
            {
                "quantity": (
                    f"Insufficient stock at source (have {bal_from.quantity}, need {quantity})."
                )
            }
        )
    bal_from.quantity -= quantity
    bal_from.save(update_fields=["quantity", "updated_at"])

    mov_out = StockMovement.objects.create(
        tenant_id=tenant_id,
        outlet=from_outlet,
        menu_item=menu_item,
        quantity_change=-quantity,
        reason=StockReason.TRANSFER_OUT,
        transfer_batch=batch,
        created_by=user,
        note=note_text,
    )

    bal_to, _ = StockBalance.objects.select_for_update().get_or_create(
        outlet=to_outlet,
        menu_item=menu_item,
        defaults={"tenant_id": tenant_id, "quantity": Decimal("0")},
    )
    bal_to.quantity += quantity
    bal_to.save(update_fields=["quantity", "updated_at"])

    mov_in = StockMovement.objects.create(
        tenant_id=tenant_id,
        outlet=to_outlet,
        menu_item=menu_item,
        quantity_change=quantity,
        reason=StockReason.TRANSFER_IN,
        transfer_batch=batch,
        created_by=user,
        note=note_text,
    )

    log_audit(
        tenant_id=tenant_id,
        user_id=user.id if user else None,
        action="stock.transfer",
        entity_type="stock_transfer",
        entity_id=str(batch),
        payload={
            "from_outlet_id": str(from_outlet.id),
            "to_outlet_id": str(to_outlet.id),
            "menu_item_id": str(menu_item.id),
            "quantity": str(quantity),
        },
    )
    return batch, mov_out, mov_in


@transaction.atomic
def complete_stock_count_session(
    *,
    session: StockCountSession,
    resolved_lines: list[dict],
    user,
    membership: Membership,
) -> StockCountSession:
    session = StockCountSession.objects.select_for_update().get(pk=session.pk)
    if session.status != StockCountStatus.DRAFT:
        raise ValidationError("Only draft sessions can be completed.")
    if not outlet_belongs_to_membership(membership, session.outlet_id):
        raise ValidationError("You cannot complete counts for this outlet.")
    if not resolved_lines:
        raise ValidationError({"lines": "At least one line is required."})

    from apps.pos.services import menu_item_available_at_outlet

    tenant_id = session.tenant_id
    outlet_id = session.outlet_id

    rows = sorted(resolved_lines, key=lambda r: str(r["menu_item"].id))
    for row in rows:
        mi = row["menu_item"]
        if mi.tenant_id != tenant_id:
            raise ValidationError({"lines": "Invalid menu item for this tenant."})
        if not mi.track_inventory:
            raise ValidationError(
                {"lines": f'"{mi.name}" does not track inventory.'}
            )
        if not menu_item_available_at_outlet(mi, outlet_id):
            raise ValidationError(
                {"lines": f'"{mi.name}" is not available at this outlet.'}
            )

    for row in rows:
        mi = row["menu_item"]
        counted = row["counted_quantity"]
        bal, _ = StockBalance.objects.select_for_update().get_or_create(
            outlet_id=outlet_id,
            menu_item=mi,
            defaults={"tenant_id": tenant_id, "quantity": Decimal("0")},
        )
        before = bal.quantity
        delta = counted - before
        bal.quantity = counted
        bal.save(update_fields=["quantity", "updated_at"])
        if delta != 0:
            StockMovement.objects.create(
                tenant_id=tenant_id,
                outlet_id=outlet_id,
                menu_item=mi,
                quantity_change=delta,
                reason=StockReason.PHYSICAL_COUNT,
                created_by=user,
                note=f"stock count {session.id}"[:512],
            )
        StockCountLine.objects.create(
            session=session,
            menu_item=mi,
            counted_quantity=counted,
            system_quantity_before=before,
            variance=delta,
        )

    session.status = StockCountStatus.COMPLETED
    session.completed_at = timezone.now()
    session.save(update_fields=["status", "completed_at", "updated_at"])

    log_audit(
        tenant_id=tenant_id,
        user_id=user.id if user else None,
        action="stock.count_completed",
        entity_type="stock_count_session",
        entity_id=str(session.id),
        payload={"line_count": len(rows), "outlet_id": str(outlet_id)},
    )
    return session
