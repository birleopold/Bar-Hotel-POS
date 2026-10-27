import uuid
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import Membership
from apps.audit.services import log_audit
from apps.pos.models import Order

from .costing import authoritative_unit_cost
from .models import (
    StockBalance,
    StockCountLine,
    StockCountSession,
    StockCountStatus,
    StockMovement,
    StockReason,
    StockTransferReceipt,
    RetailAssemblyRun,
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
    allow_serialized: bool = False,
) -> StockMovement:
    """Apply a non-sale movement and update ``StockBalance``.

    Validate tenant scope and quantities before posting a financial stock fact.
    """
    try:
        quantity_change = Decimal(str(quantity_change))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ValidationError({"quantity_change": "Enter a valid stock quantity."}) from exc
    if (not quantity_change.is_finite()
            or quantity_change == 0
            or quantity_change != quantity_change.quantize(Decimal("0.001"))
            or abs(quantity_change) > Decimal("99999999999.999")):
        raise ValidationError({"quantity_change": "Enter a non-zero quantity with up to three decimal places."})
    if outlet.site.tenant_id != tenant_id or menu_item.tenant_id != tenant_id:
        raise ValidationError({"stock": "Section and product must belong to this business."})
    if menu_item.serial_tracking and not allow_serialized:
        raise ValidationError({
            "stock": (
                f'"{menu_item.name}" is serial / IMEI tracked. '
                "Use a serialized receiving, sale, return or transfer workflow so physical identifiers stay in sync."
            )
        })

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
    batch_allocations = []
    if quantity_change < 0:
        from .services_batches import consume_for_outflow_if_batched
        batch_allocations = consume_for_outflow_if_batched(
            tenant_id=tenant_id, outlet_id=outlet.id, menu_item_id=menu_item.id,
            quantity=-quantity_change,
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
    if batch_allocations:
        from .services_batches import record_batch_allocations
        record_batch_allocations(
            tenant_id=tenant_id, movement=movement, allocations=batch_allocations,
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
    """Consume tracked sales and recipe ingredients only after full settlement.

    Aggregate the *combined* requirement before posting any movement. A
    tracked product may also be a recipe ingredient elsewhere in this order:
    checking sale and recipe requirements independently would overdraw it.
    Caller runs inside the payment settlement transaction.
    """
    from apps.catalog.models import MenuItem
    from .services_batches import consume_for_outflow_if_batched, record_batch_allocations

    from .services_serials import (
        mark_serial_assignments_sold,
        validate_serial_assignments_for_order,
    )

    tenant_id = order.tenant_id
    outlet_id = order.outlet_id
    serial_assignments = validate_serial_assignments_for_order(order=order)
    sale_need: dict = {}
    recipe_need: dict = {}
    item_names: dict = {}

    for line in (
        order.lines.filter(is_voided=False, menu_item__isnull=False)
        .select_related("menu_item")
        .prefetch_related("menu_item__recipe_lines__ingredient_item")
    ):
        item = line.menu_item
        if item.track_inventory:
            sale_need[item.pk] = sale_need.get(item.pk, Decimal("0")) + line.quantity
            item_names[item.pk] = item.name
        if not item.consume_recipe_on_sale:
            continue
        for recipe_line in item.recipe_lines.all():
            ingredient = recipe_line.ingredient_item
            if not ingredient.track_inventory:
                continue
            need = (line.quantity * recipe_line.quantity_per_unit).quantize(Decimal("0.001"))
            recipe_need[ingredient.pk] = recipe_need.get(ingredient.pk, Decimal("0")) + need
            item_names[ingredient.pk] = ingredient.name

    all_ids = sorted(set(sale_need) | set(recipe_need), key=str)
    # Lock all affected stock rows deterministically. This also prevents two
    # simultaneous checkouts from approving the same last units.
    balances = {}
    for item_id in all_ids:
        bal, _ = StockBalance.objects.select_for_update().get_or_create(
            outlet_id=outlet_id, menu_item_id=item_id,
            defaults={"tenant_id": tenant_id, "quantity": Decimal("0")},
        )
        need = sale_need.get(item_id, Decimal("0")) + recipe_need.get(item_id, Decimal("0"))
        if need <= 0:
            continue
        if bal.quantity < need:
            raise ValidationError({
                "stock": (
                    f'Insufficient stock for "{item_names[item_id]}" '
                    f"(need {need}, have {bal.quantity})."
                )
            })
        balances[item_id] = bal

    # Snapshot authoritative outlet cost onto directly sold inventory lines
    # before decrementing stock. Historical sales never change if future
    # receipts alter the weighted average.
    for line in order.lines.filter(
        is_voided=False,
        menu_item__isnull=False,
        menu_item_id__in=sale_need.keys(),
    ):
        balance = balances.get(line.menu_item_id)
        cost = authoritative_unit_cost(balance) if balance is not None else None
        line.cost_unit_snapshot = cost
        line.cost_basis_complete_snapshot = cost is not None
        line.save(update_fields=[
            "cost_unit_snapshot",
            "cost_basis_complete_snapshot",
            "updated_at",
        ])

    # Keep movement reasons separate for reliable sales and recipe reporting,
    # but validate their *combined* requirement first. All writes are part of
    # the caller's atomic payment transaction.
    for requirements, reason in (
        (sale_need, StockReason.SALE),
        (recipe_need, StockReason.RECIPE),
    ):
        for item_id, need in sorted(requirements.items(), key=lambda row: str(row[0])):
            if need <= 0:
                continue
            bal = balances[item_id]
            allocations = consume_for_outflow_if_batched(
                tenant_id=tenant_id, outlet_id=outlet_id,
                menu_item_id=item_id, quantity=need,
            )
            bal.quantity -= need
            bal.save(update_fields=["quantity", "updated_at"])
            movement = StockMovement.objects.create(
                tenant_id=tenant_id, outlet_id=outlet_id,
                menu_item_id=item_id, quantity_change=-need,
                reason=reason, order=order, created_by=user,
            )
            if allocations:
                record_batch_allocations(
                    tenant_id=tenant_id, movement=movement, allocations=allocations,
                )

    mark_serial_assignments_sold(
        order=order,
        assignments=serial_assignments,
        user=user,
    )


@transaction.atomic
def execute_retail_assembly(
    *,
    tenant_id,
    outlet,
    assembled_item,
    quantity,
    direction,
    user,
    membership,
    note="",
) -> RetailAssemblyRun:
    """Build or unbuild a retail assembly using the authoritative stock ledger."""

    from apps.inventory.batches import InventoryBatch

    if not outlet_belongs_to_membership(membership, outlet.id):
        raise ValidationError({"outlet": "You cannot assemble stock for this outlet."})
    if outlet.site.tenant_id != tenant_id or assembled_item.tenant_id != tenant_id:
        raise ValidationError({"assembly": "Outlet and finished product must belong to this business."})
    if direction not in RetailAssemblyRun.Direction.values:
        raise ValidationError({"direction": "Choose build or unbuild."})
    if not assembled_item.track_inventory:
        raise ValidationError({"assembly": "Enable stock tracking on the finished product first."})
    if assembled_item.serial_tracking:
        raise ValidationError({"assembly": "Serialized finished products require a dedicated serial-aware assembly workflow."})
    try:
        qty = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"quantity": "Enter a valid assembly quantity."}) from exc
    if (
        not qty.is_finite()
        or qty <= 0
        or qty > Decimal("99999999999.999")
        or qty != qty.quantize(Decimal("0.001"))
    ):
        raise ValidationError({"quantity": "Enter a positive quantity with up to three decimal places."})
    if assembled_item.unit_of_measure == "each" and qty != qty.to_integral_value():
        raise ValidationError({"quantity": "Piece-based finished products must be built in whole units."})

    components = list(
        assembled_item.assembly_components.select_related("component_item")
        .filter(tenant_id=tenant_id)
        .order_by("component_item_id")
    )
    if not components:
        raise ValidationError({"assembly": "Configure at least one retail assembly component first."})
    component_need = {}
    item_names = {assembled_item.pk: assembled_item.name}
    for line in components:
        component = line.component_item
        if component.tenant_id != tenant_id:
            raise ValidationError({"assembly": "Assembly contains a component from another business."})
        if not component.track_inventory:
            raise ValidationError({"assembly": f'Enable stock tracking on component "{component.name}".'})
        if component.serial_tracking:
            raise ValidationError({"assembly": f'Serialized component "{component.name}" requires serial-aware assembly allocation.'})
        need = (qty * line.quantity_per_unit).quantize(Decimal("0.001"))
        if need <= 0 or need > Decimal("99999999999.999"):
            raise ValidationError({"assembly": f'Invalid component requirement for "{component.name}".'})
        component_need[component.pk] = component_need.get(component.pk, Decimal("0")) + need
        item_names[component.pk] = component.name

    all_item_ids = sorted({assembled_item.pk, *component_need.keys()}, key=str)
    balances = {}
    for item_id in all_item_ids:
        balance, _ = StockBalance.objects.select_for_update().get_or_create(
            tenant_id=tenant_id,
            outlet=outlet,
            menu_item_id=item_id,
            defaults={"quantity": Decimal("0")},
        )
        balances[item_id] = balance

    # Batch intake uses the same StockBalance lock before creating a lot. Check
    # only after all balances are locked so a concurrent batch receipt cannot
    # appear between this guard and the assembly stock movements.
    if InventoryBatch.objects.filter(
        tenant_id=tenant_id,
        outlet_id=outlet.id,
        menu_item_id__in=all_item_ids,
    ).exists():
        raise ValidationError({
            "assembly": (
                "This assembly contains batch/expiry-tracked stock. "
                "Lot-aware assembly allocation must be configured before build/unbuild."
            )
        })

    if direction == RetailAssemblyRun.Direction.BUILD:
        for item_id, need in component_need.items():
            if balances[item_id].quantity < need:
                raise ValidationError({
                    "stock": (
                        f'Insufficient "{item_names[item_id]}" for this build '
                        f"(need {need}, have {balances[item_id].quantity})."
                    )
                })
    else:
        if balances[assembled_item.pk].quantity < qty:
            raise ValidationError({
                "stock": (
                    f'Insufficient "{assembled_item.name}" to unbuild '
                    f"(need {qty}, have {balances[assembled_item.pk].quantity})."
                )
            })

    run = RetailAssemblyRun.objects.create(
        tenant_id=tenant_id,
        outlet=outlet,
        assembled_item=assembled_item,
        direction=direction,
        quantity=qty,
        note=(note or "")[:512],
        created_by=user,
    )
    movement_note = (
        f"{run.get_direction_display()} {assembled_item.name} · run {run.pk}"
    )[:512]

    def post(item_id, change):
        balance = balances[item_id]
        new_qty = balance.quantity + change
        if new_qty < 0:
            raise ValidationError({"stock": f'Assembly would make "{item_names[item_id]}" negative.'})
        if new_qty > Decimal("99999999999.999"):
            raise ValidationError({"stock": f'Assembly would exceed the stock limit for "{item_names[item_id]}".'})
        balance.quantity = new_qty
        balance.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            tenant_id=tenant_id,
            outlet=outlet,
            menu_item_id=item_id,
            quantity_change=change,
            reason=(
                StockReason.ASSEMBLY_BUILD
                if direction == RetailAssemblyRun.Direction.BUILD
                else StockReason.ASSEMBLY_UNBUILD
            ),
            created_by=user,
            note=movement_note,
            assembly_run=run,
        )

    if direction == RetailAssemblyRun.Direction.BUILD:
        for item_id, need in sorted(component_need.items(), key=lambda row: str(row[0])):
            post(item_id, -need)
        post(assembled_item.pk, qty)
    else:
        post(assembled_item.pk, -qty)
        for item_id, need in sorted(component_need.items(), key=lambda row: str(row[0])):
            post(item_id, need)

    log_audit(
        tenant_id=tenant_id,
        user_id=user.pk if user else None,
        action=f"inventory.assembly_{direction}",
        entity_type="retail_assembly_run",
        entity_id=str(run.pk),
        payload={
            "outlet_id": str(outlet.pk),
            "assembled_item_id": str(assembled_item.pk),
            "quantity": str(qty),
            "components": {
                str(item_id): str(need) for item_id, need in component_need.items()
            },
        },
    )
    return run


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
    staged: bool = False,
) -> tuple[uuid.UUID, StockMovement, StockMovement | None]:
    try:
        quantity = Decimal(str(quantity))
    except (TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
        raise ValidationError({"quantity": "Enter a valid transfer quantity."}) from exc
    if (not quantity.is_finite() or quantity <= 0
            or quantity > Decimal("99999999999.999")
            or quantity != quantity.quantize(Decimal("0.001"))):
        raise ValidationError({"quantity": "Transfer quantity must be positive with up to three decimal places."})
    if from_outlet.id == to_outlet.id:
        raise ValidationError({"to_outlet": "Destination must differ from source."})
    if from_outlet.site.tenant_id != tenant_id or to_outlet.site.tenant_id != tenant_id:
        raise ValidationError("Outlets must belong to the current tenant.")
    if not outlet_belongs_to_membership(membership, from_outlet.id):
        raise ValidationError({"from_outlet": "You cannot transfer from this outlet."})
    if not outlet_belongs_to_membership(membership, to_outlet.id):
        raise ValidationError({"to_outlet": "You cannot transfer to this outlet."})
    if menu_item.tenant_id != tenant_id:
        raise ValidationError({"menu_item": "Product must belong to this business."})
    if not menu_item.track_inventory:
        raise ValidationError({"menu_item": "Enable track_inventory on this item."})
    if menu_item.serial_tracking:
        raise ValidationError({
            "menu_item": (
                "Serialized products require identifier-specific transfer handling. "
                "Use the serial / IMEI workflow instead of aggregate stock transfer."
            )
        })

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
    from .services_batches import consume_for_outflow_if_batched
    source_batches = consume_for_outflow_if_batched(
        tenant_id=tenant_id, outlet_id=from_outlet.id,
        menu_item_id=menu_item.id, quantity=quantity,
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
    from .services_batches import record_batch_allocations
    if source_batches:
        record_batch_allocations(
            tenant_id=tenant_id, movement=mov_out, allocations=source_batches,
        )

    if staged:
        StockTransferReceipt.objects.create(
            tenant_id=tenant_id, transfer_batch=batch, from_outlet=from_outlet,
            to_outlet=to_outlet, menu_item=menu_item, dispatched_quantity=quantity,
            dispatched_by=user, mode="staged", status="in_transit",
        )
        log_audit(
            tenant_id=tenant_id, user_id=user.pk if user else None,
            action="stock.transfer_dispatched", entity_type="stock_transfer",
            entity_id=str(batch), payload={
                "from_outlet_id": str(from_outlet.id), "to_outlet_id": str(to_outlet.id),
                "menu_item_id": str(menu_item.id), "quantity": str(quantity),
            },
        )
        return batch, mov_out, None

    bal_to, _ = StockBalance.objects.select_for_update().get_or_create(
        outlet=to_outlet,
        menu_item=menu_item,
        defaults={"tenant_id": tenant_id, "quantity": Decimal("0")},
    )
    bal_to.quantity += quantity
    bal_to.save(update_fields=["quantity", "updated_at"])
    destination_allocations = []
    if source_batches:
        from .batches import InventoryBatch
        from django.utils import timezone
        from django.db.models import F
        for source_batch_id, used in source_batches:
            source = InventoryBatch.objects.get(pk=source_batch_id)
            destination, created = InventoryBatch.objects.get_or_create(
                tenant_id=tenant_id, outlet=to_outlet, menu_item=menu_item,
                batch_code=source.batch_code,
                defaults={
                    "received_at": timezone.localdate(),
                    "expiry_date": source.expiry_date,
                    "received_quantity": used,
                    "remaining_quantity": used,
                    "quarantined": source.quarantined,
                },
            )
            if not created:
                if destination.expiry_date != source.expiry_date or destination.quarantined:
                    raise ValidationError({"stock": "Destination has an incompatible or held batch with the same code."})
                InventoryBatch.objects.filter(pk=destination.pk).update(
                    received_quantity=F("received_quantity") + used,
                    remaining_quantity=F("remaining_quantity") + used,
                )
            destination_allocations.append((destination.pk, used))

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

    if destination_allocations:
        record_batch_allocations(
            tenant_id=tenant_id, movement=mov_in, allocations=destination_allocations,
        )
    StockTransferReceipt.objects.create(
        tenant_id=tenant_id, transfer_batch=batch, from_outlet=from_outlet,
        to_outlet=to_outlet, menu_item=menu_item, dispatched_quantity=quantity,
        dispatched_by=user,
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
    from apps.staff.services.permissions import membership_has_inventory_capability

    session = StockCountSession.objects.select_for_update().get(pk=session.pk)
    if not membership_has_inventory_capability(membership, "approve_count"):
        raise ValidationError("Only an authorized manager can finalize stock count adjustments.")
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
    seen_items = set()
    for row in rows:
        mi = row["menu_item"]
        # Preflight every count before changing the first balance. The model
        # permits one count line per item; reject duplicate and malformed
        # values here with a clear error instead of an IntegrityError or a
        # partially changed inventory ledger.
        if mi.id in seen_items:
            raise ValidationError({"lines": f'Duplicate count for "{mi.name}".'})
        seen_items.add(mi.id)
        try:
            counted = Decimal(str(row["counted_quantity"]))
        except (TypeError, ValueError, ArithmeticError, KeyError, InvalidOperation) as exc:
            raise ValidationError({"lines": f'Invalid count for "{mi.name}".'}) from exc
        if (
            not counted.is_finite()
            or counted < 0
            or counted > Decimal("99999999999.999")
            or counted != counted.quantize(Decimal("0.001"))
        ):
            raise ValidationError({"lines": f'Invalid count for "{mi.name}": use a non-negative quantity with up to 3 decimals.'})
        row["counted_quantity"] = counted
        if mi.tenant_id != tenant_id:
            raise ValidationError({"lines": "Invalid menu item for this tenant."})
        if not mi.track_inventory:
            raise ValidationError(
                {"lines": f'"{mi.name}" does not track inventory.'}
            )
        if mi.serial_tracking:
            raise ValidationError({
                "lines": (
                    f'"{mi.name}" is serial / IMEI tracked. '
                    "Serialized stock counts must reconcile identifiers, not only aggregate quantity."
                )
            })
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
        if counted < 0:
            raise ValidationError({"lines": "A physical count cannot be negative."})
        count_allocations = []
        if delta < 0:
            from .services_batches import consume_for_outflow_if_batched
            count_allocations = consume_for_outflow_if_batched(
                tenant_id=tenant_id, outlet_id=outlet_id,
                menu_item_id=mi.id, quantity=-delta,
            )
        bal.quantity = counted
        bal.save(update_fields=["quantity", "updated_at"])
        if delta != 0:
            movement = StockMovement.objects.create(
                tenant_id=tenant_id,
                outlet_id=outlet_id,
                menu_item=mi,
                quantity_change=delta,
                reason=StockReason.PHYSICAL_COUNT,
                created_by=user,
                note=f"stock count {session.id}"[:512],
            )
            if count_allocations:
                from .services_batches import record_batch_allocations
                record_batch_allocations(
                    tenant_id=tenant_id, movement=movement, allocations=count_allocations,
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


# Review is separate from posting a physical-count adjustment. The locked
# submission baseline must still be current when a second worker approves.
@transaction.atomic
def submit_stock_count_for_review(*, session, resolved_lines, user, membership):
    from apps.pos.services import menu_item_available_at_outlet
    from apps.staff.services.permissions import membership_has_inventory_capability

    session = StockCountSession.objects.select_for_update().get(pk=session.pk)
    if session.status != StockCountStatus.DRAFT:
        raise ValidationError("Only draft counts can be submitted.")
    if not membership_has_inventory_capability(membership, "count"):
        raise ValidationError("Your role cannot count inventory.")
    if not outlet_belongs_to_membership(membership, session.outlet_id):
        raise ValidationError("You cannot count stock for this outlet.")
    if not resolved_lines:
        raise ValidationError({"lines": "Enter at least one physical quantity."})
    if session.lines.exists():
        raise ValidationError("Count lines already exist; refresh the session.")
    seen = set()
    for row in sorted(resolved_lines, key=lambda x: str(x["menu_item"].pk)):
        item = row["menu_item"]
        if item.id in seen:
            raise ValidationError({"lines": f'Duplicate count for "{item.name}".'})
        seen.add(item.id)
        try:
            quantity = Decimal(str(row["counted_quantity"]))
        except (ValueError, TypeError, ArithmeticError, KeyError, InvalidOperation) as exc:
            raise ValidationError({"lines": f'Invalid count for "{item.name}".'}) from exc
        if (not quantity.is_finite() or quantity < 0
                or quantity > Decimal("99999999999.999")
                or quantity != quantity.quantize(Decimal("0.001"))):
            raise ValidationError({"lines": f'Invalid count for "{item.name}".'})
        if (item.tenant_id != session.tenant_id or not item.track_inventory
                or not menu_item_available_at_outlet(item, session.outlet_id)):
            raise ValidationError({"lines": f'"{item.name}" is not a tracked product at this section.'})
        if item.serial_tracking:
            raise ValidationError({
                "lines": (
                    f'"{item.name}" is serial / IMEI tracked. '
                    "Use the serialized inventory register to reconcile physical identifiers."
                )
            })
        bal = StockBalance.objects.select_for_update().filter(
            tenant_id=session.tenant_id, outlet_id=session.outlet_id, menu_item_id=item.id,
        ).first()
        before = bal.quantity if bal else Decimal("0")
        StockCountLine.objects.create(
            session=session, menu_item=item, counted_quantity=quantity,
            system_quantity_before=before, variance=quantity - before,
        )
    session.status = StockCountStatus.REVIEW
    session.submitted_by = user
    session.submitted_at = timezone.now()
    session.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])
    log_audit(
        tenant_id=session.tenant_id, user_id=user.id, action="stock.count_submitted",
        entity_type="stock_count_session", entity_id=str(session.id),
        payload={"line_count": len(seen), "outlet_id": str(session.outlet_id)},
    )
    return session


def _assert_count_approver(session, user, membership):
    from apps.staff.services.permissions import membership_has_inventory_capability
    if (not membership_has_inventory_capability(membership, "approve_count")
            or not outlet_belongs_to_membership(membership, session.outlet_id)):
        raise ValidationError("An authorized manager is required for this section.")
    if user is None or user.id == session.submitted_by_id:
        raise ValidationError("A different manager must approve this count.")


@transaction.atomic
def approve_stock_count_session(*, session, user, membership):
    session = StockCountSession.objects.select_for_update().get(pk=session.pk)
    if session.status != StockCountStatus.REVIEW:
        raise ValidationError("Only submitted counts can be approved.")
    _assert_count_approver(session, user, membership)
    lines = list(session.lines.select_related("menu_item").order_by("menu_item_id"))
    if not lines:
        raise ValidationError("The submission has no counted items.")
    # Lock balances in deterministic order: the same order used by final posting.
    # Refuse a stale physical reading rather than undoing a sale/receipt/transfer.
    for line in lines:
        balance = StockBalance.objects.select_for_update().filter(
            tenant_id=session.tenant_id, outlet_id=session.outlet_id,
            menu_item_id=line.menu_item_id,
        ).first()
        now = balance.quantity if balance else Decimal("0")
        # A sale followed by a return may produce the same net quantity but
        # invalidate the physical snapshot or its batch/expiry composition.
        intervening_movement = StockMovement.objects.filter(
            tenant_id=session.tenant_id, outlet_id=session.outlet_id,
            menu_item_id=line.menu_item_id, created_at__gt=session.submitted_at,
        ).exists()
        if now != line.system_quantity_before or intervening_movement:
            raise ValidationError({
                "stock": f'"{line.menu_item.name}" changed since counting. Return it for a fresh count.'
            })
    # One database transaction: historic submitted quantities remain in the
    # audit event, and completion recreates the same lines with posted movements.
    session.lines.all().delete()
    session.status = StockCountStatus.DRAFT
    session.save(update_fields=["status", "updated_at"])
    complete_stock_count_session(
        session=session,
        resolved_lines=[
            {"menu_item": line.menu_item, "counted_quantity": line.counted_quantity}
            for line in lines
        ],
        user=user, membership=membership,
    )
    session.refresh_from_db()
    session.approved_by = user
    session.save(update_fields=["approved_by", "updated_at"])
    log_audit(
        tenant_id=session.tenant_id, user_id=user.id, action="stock.count_approved",
        entity_type="stock_count_session", entity_id=str(session.id),
        payload={"submitted_by_id": str(session.submitted_by_id), "line_count": len(lines)},
    )
    return session


@transaction.atomic
def return_stock_count_for_recount(*, session, user, membership, reason):
    from apps.staff.services.permissions import membership_has_inventory_capability
    session = StockCountSession.objects.select_for_update().get(pk=session.pk)
    if session.status != StockCountStatus.REVIEW:
        raise ValidationError("Only submitted counts can be returned for recount.")
    if (not membership_has_inventory_capability(membership, "approve_count")
            or not outlet_belongs_to_membership(membership, session.outlet_id)):
        raise ValidationError("An authorized manager is required for this section.")
    reason = (reason or "").strip()
    if not reason or len(reason) > 512:
        raise ValidationError({"reason": "Explain the recount (maximum 512 characters)."})
    rejected_lines = [
        {
            "menu_item_id": str(line.menu_item_id),
            "counted": str(line.counted_quantity),
            "expected": str(line.system_quantity_before),
            "variance": str(line.variance),
        }
        for line in session.lines.all().order_by("menu_item_id")
    ]
    session.lines.all().delete()
    session.status = StockCountStatus.DRAFT
    session.submitted_by = None
    session.submitted_at = None
    session.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])
    log_audit(
        tenant_id=session.tenant_id, user_id=user.id,
        action="stock.count_recount_requested", entity_type="stock_count_session",
        entity_id=str(session.id),
        payload={"reason": reason, "rejected_snapshot": rejected_lines},
    )
    return session


@transaction.atomic
def verify_stock_transfer_receipt(*, receipt, membership, user, received_quantity, note=""):
    """Account for a physical receipt without reposting any stock movement."""
    from apps.staff.services.permissions import membership_has_inventory_capability
    receipt = StockTransferReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.status not in ("awaiting", "in_transit"):
        raise ValidationError("This transfer has already been checked.")
    if not membership_has_inventory_capability(membership, "transfer"):
        raise ValidationError("You cannot verify stock transfers.")
    if membership.tenant_id != receipt.tenant_id or not outlet_belongs_to_membership(membership, receipt.to_outlet_id):
        raise ValidationError("You cannot verify stock for the destination section.")
    if user is None or user.pk == receipt.dispatched_by_id:
        raise ValidationError("A different receiving worker must check this transfer.")
    try:
        amount = Decimal(str(received_quantity))
    except (TypeError, ValueError, InvalidOperation, ArithmeticError) as exc:
        raise ValidationError({"received_quantity": "Enter a valid physical quantity."}) from exc
    if (not amount.is_finite() or amount < 0 or amount > Decimal("99999999999.999")
            or amount != amount.quantize(Decimal("0.001"))):
        raise ValidationError({"received_quantity": "Enter a non-negative quantity, up to three decimal places."})
    note = (note or "").strip()
    if len(note) > 512:
        raise ValidationError({"note": "Limit the explanation to 512 characters."})
    if amount != receipt.dispatched_quantity and not note:
        raise ValidationError({"note": "Explain the missing or extra stock before reporting a discrepancy."})
    if receipt.mode == "staged":
        posted = min(amount, receipt.dispatched_quantity)
        _post_staged_transfer_arrival(
            receipt=receipt, quantity=posted, destination=receipt.to_outlet,
            user=user, note="Physical receiving: " + note,
        )
        receipt.posted_quantity = posted
    receipt.received_quantity = amount
    receipt.status = "matched" if amount == receipt.dispatched_quantity else "disputed"
    receipt.discrepancy_note = note
    receipt.checked_by = user
    receipt.checked_at = timezone.now()
    receipt.save(update_fields=[
        "received_quantity", "status", "discrepancy_note",
        "checked_by", "checked_at", "posted_quantity", "updated_at",
    ])
    log_audit(
        tenant_id=receipt.tenant_id, user_id=user.pk,
        action="stock.transfer_verified", entity_type="stock_transfer",
        entity_id=str(receipt.transfer_batch),
        payload={
            "from_outlet_id": str(receipt.from_outlet_id), "to_outlet_id": str(receipt.to_outlet_id),
            "dispatched": str(receipt.dispatched_quantity), "received": str(amount),
            "status": receipt.status, "note": note,
        },
    )
    return receipt



@transaction.atomic
def review_stock_transfer_discrepancy(*, receipt, membership, user, review_action, note):
    """Record independent manager follow-up; never rewrite posted stock.

    A disputed transfer already posted inventory at dispatch. Reconciliation
    requires a separately approved physical stock count or manual adjustment.
    This action records an investigation and cannot itself fix a variance.
    """
    from apps.staff.services.permissions import membership_has_inventory_capability

    receipt = StockTransferReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.mode != "instant":
        raise ValidationError("Staged transfers require stock-aware discrepancy resolution.")
    if receipt.status != "disputed":
        raise ValidationError("Only a delivery with a recorded discrepancy can be reviewed.")
    if receipt.reviewed_at is not None:
        raise ValidationError("This discrepancy has already been reviewed.")
    if not membership_has_inventory_capability(membership, "approve_count"):
        raise ValidationError("Only a manager can review delivery discrepancies.")
    if membership.tenant_id != receipt.tenant_id or not outlet_belongs_to_membership(
        membership, receipt.to_outlet_id,
    ):
        raise ValidationError("You cannot review the destination section.")
    if user is None or user.pk in (receipt.checked_by_id, receipt.dispatched_by_id):
        raise ValidationError("A different manager must review this delivery.")
    if review_action not in ("needs_count", "documented"):
        raise ValidationError({"review_action": "Choose a valid follow-up result."})
    note = (note or "").strip()
    if not 12 <= len(note) <= 512:
        raise ValidationError({"note": "Explain the manager's findings in 12–512 characters."})
    receipt.review_action = review_action
    receipt.review_note = note
    receipt.reviewed_by = user
    receipt.reviewed_at = timezone.now()
    receipt.save(update_fields=[
        "review_action", "review_note", "reviewed_by", "reviewed_at", "updated_at",
    ])
    log_audit(
        tenant_id=receipt.tenant_id, user_id=user.pk,
        action="stock.transfer_discrepancy_reviewed", entity_type="stock_transfer",
        entity_id=str(receipt.transfer_batch),
        payload={
            "receipt_id": str(receipt.pk),
            "from_outlet_id": str(receipt.from_outlet_id),
            "to_outlet_id": str(receipt.to_outlet_id),
            "menu_item_id": str(receipt.menu_item_id),
            "dispatched": str(receipt.dispatched_quantity),
            "received": str(receipt.received_quantity),
            "review_action": review_action, "reason": note,
            "stock_posted_by_review": False,
        },
    )
    return receipt


def _post_staged_transfer_arrival(*, receipt, quantity, destination, user, note):
    """Move confirmed units from transit to physical stock with source batch traceability.

    Caller holds the transfer receipt's row lock inside a transaction. All balance,
    batch and ledger writes roll back together when receiving is invalid.
    """
    if quantity <= 0:
        return None
    from .batches import InventoryBatch
    from .models import StockBatchAllocation
    from django.db.models import F

    dispatch_movement = StockMovement.objects.get(
        tenant_id=receipt.tenant_id, transfer_batch=receipt.transfer_batch,
        reason=StockReason.TRANSFER_OUT, outlet_id=receipt.from_outlet_id,
    )
    source_allocations = list(
        StockBatchAllocation.objects.filter(stock_movement=dispatch_movement)
        .select_related("batch").order_by("created_at", "id")
    )
    prior_posted = receipt.posted_quantity + receipt.returned_quantity
    if source_allocations and sum(
        (row.quantity for row in source_allocations), Decimal("0")
    ) != receipt.dispatched_quantity:
        raise ValidationError("Original dispatch allocations need reconciliation.")

    assignments = []
    remaining = quantity
    skip = prior_posted
    for allocation in source_allocations:
        if skip >= allocation.quantity:
            skip -= allocation.quantity
            continue
        available = allocation.quantity - skip
        skip = Decimal("0")
        used = min(available, remaining)
        if used <= 0:
            break
        source = allocation.batch
        receiving_batch, created = InventoryBatch.objects.select_for_update().get_or_create(
            tenant_id=receipt.tenant_id, outlet=destination, menu_item=receipt.menu_item,
            batch_code=source.batch_code,
            defaults={
                "received_at": timezone.localdate(), "expiry_date": source.expiry_date,
                "received_quantity": used, "remaining_quantity": used,
                "quarantined": source.quarantined or bool(
                    source.expiry_date and source.expiry_date < timezone.localdate()
                ),
            },
        )
        if not created:
            if receiving_batch.expiry_date != source.expiry_date or receiving_batch.quarantined:
                raise ValidationError(
                    "The receiving section has an incompatible or held batch with that code."
                )
            InventoryBatch.objects.filter(pk=receiving_batch.pk).update(
                received_quantity=F("received_quantity") + used,
                remaining_quantity=F("remaining_quantity") + used,
            )
        assignments.append((receiving_batch.pk, used))
        remaining -= used
        if not remaining:
            break
    if source_allocations and remaining != 0:
        raise ValidationError("Receipt exceeds dispatched batch allocations.")
    bal, _ = StockBalance.objects.select_for_update().get_or_create(
        outlet=destination, menu_item=receipt.menu_item,
        defaults={"tenant_id": receipt.tenant_id, "quantity": Decimal("0")},
    )
    bal.quantity += quantity
    bal.save(update_fields=["quantity", "updated_at"])
    movement = StockMovement.objects.create(
        tenant_id=receipt.tenant_id, outlet=destination, menu_item=receipt.menu_item,
        quantity_change=quantity, reason=StockReason.TRANSFER_IN,
        transfer_batch=receipt.transfer_batch, created_by=user, note=note[:512],
    )
    if assignments:
        from .services_batches import record_batch_allocations
        record_batch_allocations(
            tenant_id=receipt.tenant_id, movement=movement, allocations=assignments,
        )
    return movement


@transaction.atomic
def resolve_stock_transfer_discrepancy(*, receipt, membership, user, action, note):
    """Record an independent manager's final decision and any necessary stock movement."""
    from apps.staff.services.permissions import membership_has_inventory_capability
    receipt = StockTransferReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.mode != "staged" or receipt.status != "disputed":
        raise ValidationError("Only an open staged-transfer discrepancy can be resolved.")
    if (
        membership.tenant_id != receipt.tenant_id
        or not membership_has_inventory_capability(membership, "approve_count")
        or not outlet_belongs_to_membership(membership, receipt.to_outlet_id)
        or not outlet_belongs_to_membership(membership, receipt.from_outlet_id)
    ):
        raise ValidationError("A manager with access to both sections must resolve this discrepancy.")
    if user is None or user.pk in (receipt.dispatched_by_id, receipt.checked_by_id):
        raise ValidationError("An independent manager must resolve this discrepancy.")
    note = (note or "").strip()
    if not note or len(note) > 512:
        raise ValidationError({"note": "Explain the investigation and decision (up to 512 characters)."})
    outstanding = receipt.outstanding_quantity
    overage = (receipt.received_quantity or Decimal("0")) > receipt.dispatched_quantity
    if overage:
        if action != "acknowledge_overage":
            raise ValidationError("Extra goods must be investigated, not silently added to stock.")
    elif outstanding <= 0 or action not in ("receive_missing", "return_source", "write_off"):
        raise ValidationError("Choose a valid outcome for the remaining goods.")
    if action == "receive_missing":
        _post_staged_transfer_arrival(
            receipt=receipt, quantity=outstanding, destination=receipt.to_outlet,
            user=user, note="Late receipt: " + note,
        )
        receipt.posted_quantity += outstanding
    elif action == "return_source":
        _post_staged_transfer_arrival(
            receipt=receipt, quantity=outstanding, destination=receipt.from_outlet,
            user=user, note="Recovered in transit: " + note,
        )
        receipt.returned_quantity += outstanding
    elif action == "write_off":
        # Source movement already removed stock from sellable on-hand.
        receipt.written_off_quantity += outstanding
    receipt.status = "resolved"
    receipt.resolution_action = action
    receipt.resolution_note = note
    receipt.resolved_by = user
    receipt.resolved_at = timezone.now()
    receipt.save(update_fields=[
        "posted_quantity", "returned_quantity", "written_off_quantity",
        "status", "resolution_action", "resolution_note",
        "resolved_by", "resolved_at", "updated_at",
    ])
    log_audit(
        tenant_id=receipt.tenant_id, user_id=user.pk,
        action="stock.transfer_discrepancy_resolved", entity_type="stock_transfer",
        entity_id=str(receipt.transfer_batch),
        payload={
            "action": action, "note": note,
            "outstanding_before": str(outstanding),
            "posted": str(receipt.posted_quantity), "returned": str(receipt.returned_quantity),
            "written_off": str(receipt.written_off_quantity),
        },
    )
    return receipt
