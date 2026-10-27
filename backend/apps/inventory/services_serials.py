import calendar
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.access.outlets import outlet_belongs_to_membership

from .models import (
    InventorySerialEvent,
    InventorySerialReturnLink,
    InventorySerialUnit,
    SerializedUnitEventType,
    SerializedUnitStatus,
)


def _add_months(value: date, months: int | None) -> date | None:
    if not months:
        return None
    month_index = (value.month - 1) + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def normalize_serial_numbers(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = values.replace(",", "\n").splitlines()
    result = []
    seen = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        folded = value.casefold()
        if folded in seen:
            raise ValidationError({"serial_numbers": f'Duplicate identifier "{value}" in this entry.'})
        if len(value) > 128:
            raise ValidationError({"serial_numbers": "Serial / IMEI values must be 128 characters or fewer."})
        seen.add(folded)
        result.append(value)
    return result


def validate_serial_receipt(*, tenant_id, outlet, menu_item, quantity, serial_numbers) -> list[str]:
    serials = normalize_serial_numbers(serial_numbers)
    if not menu_item.serial_tracking:
        if serials:
            raise ValidationError({"serial_numbers": f"{menu_item.name} is not configured for serial / IMEI tracking."})
        return []
    if not menu_item.track_inventory or menu_item.unit_of_measure != "each":
        raise ValidationError({"serial_numbers": f"{menu_item.name} has invalid serialized-stock configuration."})
    if outlet.site.tenant_id != tenant_id or menu_item.tenant_id != tenant_id:
        raise ValidationError({"serial_numbers": "Serialized receipt scope mismatch."})
    qty = Decimal(str(quantity))
    if qty != qty.to_integral_value():
        raise ValidationError({"serial_numbers": f"{menu_item.name} requires one serial / IMEI per whole unit."})
    expected = int(qty)
    if len(serials) != expected:
        raise ValidationError({
            "serial_numbers": (
                f"{menu_item.name} is serialized: enter exactly {expected} unique "
                f"identifier{'s' if expected != 1 else ''} for the {expected} unit{'s' if expected != 1 else ''} received."
            )
        })
    from apps.catalog.models import RetailProductGroup
    group_collisions = []
    for identifier in serials:
        if RetailProductGroup.objects.filter(
            tenant_id=tenant_id,
            code__iexact=identifier,
        ).exists():
            group_collisions.append(identifier)
    if group_collisions:
        raise ValidationError({
            "serial_numbers": (
                "These identifiers are already reserved as retail group lookup codes: "
                + ", ".join(group_collisions)
            )
        })

    existing = []
    for identifier in serials:
        match = InventorySerialUnit.objects.filter(
            tenant_id=tenant_id,
            serial_number__iexact=identifier,
        ).values_list("serial_number", flat=True).first()
        if match is not None:
            existing.append(match)
    if existing:
        raise ValidationError({
            "serial_numbers": f"Already registered: {', '.join(sorted(existing))}."
        })
    return serials


def create_received_serial_units(
    *,
    tenant_id,
    outlet,
    menu_item,
    receipt_line,
    received_at,
    serial_numbers,
    user,
) -> list[InventorySerialUnit]:
    serials = validate_serial_receipt(
        tenant_id=tenant_id,
        outlet=outlet,
        menu_item=menu_item,
        quantity=receipt_line.quantity_received,
        serial_numbers=serial_numbers,
    )
    if not serials:
        return []
    units = []
    for identifier in serials:
        try:
            with transaction.atomic():
                unit = InventorySerialUnit.objects.create(
                    tenant_id=tenant_id,
                    outlet=outlet,
                    menu_item=menu_item,
                    serial_number=identifier,
                    status=SerializedUnitStatus.AVAILABLE,
                    purchase_receipt_line=receipt_line,
                    received_at=received_at,
                )
        except IntegrityError as exc:
            raise ValidationError({
                "serial_numbers": f'Serial / IMEI "{identifier}" was registered concurrently. Refresh and check the serial register.'
            }) from exc
        InventorySerialEvent.objects.create(
            tenant_id=tenant_id,
            serial_unit=unit,
            event_type=SerializedUnitEventType.RECEIVED,
            outlet=outlet,
            created_by=user,
            note=f"Received on PO {receipt_line.purchase_order_line.purchase_order.reference or receipt_line.purchase_order_line.purchase_order_id}"[:512],
        )
        units.append(unit)
    log_audit(
        tenant_id=tenant_id,
        user_id=user.pk if user else None,
        action="inventory.serials_received",
        entity_type="purchase_receipt_line",
        entity_id=str(receipt_line.pk),
        payload={
            "menu_item_id": str(menu_item.pk),
            "outlet_id": str(outlet.pk),
            "count": len(units),
            "serial_unit_ids": [str(unit.pk) for unit in units],
        },
    )
    return units


@transaction.atomic
def assign_serial_to_order_line(*, order_line, serial_number: str, user) -> InventorySerialUnit:
    line = order_line.__class__.objects.select_for_update().select_related(
        "order", "order__outlet", "menu_item"
    ).get(pk=order_line.pk)
    if line.is_voided or line.order.status != "open" or line.order.is_paid:
        raise ValidationError({"serial_number": "Serials can only be assigned to an open active sale line."})
    item = line.menu_item
    if item is None or not item.serial_tracking:
        raise ValidationError({"serial_number": "This sale line is not serial / IMEI tracked."})
    if line.quantity != line.quantity.to_integral_value():
        raise ValidationError({"serial_number": "Serialized products must use whole-unit quantities."})
    assigned = InventorySerialUnit.objects.filter(
        tenant_id=line.order.tenant_id,
        reserved_order_line=line,
        status=SerializedUnitStatus.RESERVED,
    ).count()
    if assigned >= int(line.quantity):
        raise ValidationError({"serial_number": "This sale line already has all required serials assigned."})
    identifier = (serial_number or "").strip()
    unit = (
        InventorySerialUnit.objects.select_for_update()
        .filter(
            tenant_id=line.order.tenant_id,
            outlet_id=line.order.outlet_id,
            menu_item=item,
            serial_number__iexact=identifier,
            status__in=[SerializedUnitStatus.AVAILABLE, SerializedUnitStatus.RETURNED],
            reserved_order_line__isnull=True,
        )
        .first()
    )
    if unit is None:
        raise ValidationError({"serial_number": "No available matching serial / IMEI exists for this product and section."})
    unit.status = SerializedUnitStatus.RESERVED
    unit.reserved_order_line = line
    # A previously returned unit keeps its original-sale trace in events/return
    # links. Clear the current sold pointer only when it is reserved for resale.
    unit.sold_order_line = None
    unit.sold_at = None
    unit.warranty_started_at = None
    unit.warranty_expires_at = None
    unit.save(update_fields=[
        "status", "reserved_order_line", "sold_order_line", "sold_at",
        "warranty_started_at", "warranty_expires_at", "updated_at"
    ])
    InventorySerialEvent.objects.create(
        tenant_id=line.order.tenant_id,
        serial_unit=unit,
        event_type=SerializedUnitEventType.RESERVED,
        outlet=line.order.outlet,
        order_line=line,
        created_by=user,
        note=f"Reserved for {line.order.bill_reference}"[:512],
    )
    return unit


@transaction.atomic
def release_serial_from_order_line(*, order_line, serial_unit_id, user) -> InventorySerialUnit:
    line = order_line.__class__.objects.select_for_update().select_related("order__outlet").get(pk=order_line.pk)
    if line.order.status != "open" or line.order.is_paid:
        raise ValidationError({"serial_number": "Serial reservation can only change on an open sale."})
    unit = InventorySerialUnit.objects.select_for_update().filter(
        pk=serial_unit_id,
        tenant_id=line.order.tenant_id,
        reserved_order_line=line,
        status=SerializedUnitStatus.RESERVED,
    ).first()
    if unit is None:
        raise ValidationError({"serial_number": "Reserved serial was not found on this sale line."})
    unit.status = SerializedUnitStatus.AVAILABLE
    unit.reserved_order_line = None
    unit.save(update_fields=["status", "reserved_order_line", "updated_at"])
    InventorySerialEvent.objects.create(
        tenant_id=line.order.tenant_id,
        serial_unit=unit,
        event_type=SerializedUnitEventType.RELEASED,
        outlet=line.order.outlet,
        order_line=line,
        created_by=user,
        note=f"Released from {line.order.bill_reference}"[:512],
    )
    return unit


def release_open_order_serial_reservations(*, order, user, order_line=None) -> int:
    qs = InventorySerialUnit.objects.select_for_update().filter(
        tenant_id=order.tenant_id,
        status=SerializedUnitStatus.RESERVED,
        reserved_order_line__order=order,
    )
    if order_line is not None:
        qs = qs.filter(reserved_order_line=order_line)
    units = list(qs.select_related("reserved_order_line"))
    for unit in units:
        line = unit.reserved_order_line
        unit.status = SerializedUnitStatus.AVAILABLE
        unit.reserved_order_line = None
        unit.save(update_fields=["status", "reserved_order_line", "updated_at"])
        InventorySerialEvent.objects.create(
            tenant_id=order.tenant_id,
            serial_unit=unit,
            event_type=SerializedUnitEventType.RELEASED,
            outlet=order.outlet,
            order_line=line,
            created_by=user,
            note=f"Sale line released from {order.bill_reference}"[:512],
        )
    return len(units)


def validate_serial_assignments_for_order(*, order) -> dict:
    assignments = {}
    for line in order.lines.filter(
        is_voided=False,
        menu_item__serial_tracking=True,
    ).select_related("menu_item"):
        if line.quantity != line.quantity.to_integral_value():
            raise ValidationError({
                "serials": f'{line.menu_item.name} is serialized and must use whole-unit quantity.'
            })
        units = list(
            InventorySerialUnit.objects.select_for_update().filter(
                tenant_id=order.tenant_id,
                outlet_id=order.outlet_id,
                menu_item=line.menu_item,
                reserved_order_line=line,
                status=SerializedUnitStatus.RESERVED,
                sold_order_line__isnull=True,
            ).order_by("serial_number")
        )
        expected = int(line.quantity)
        if len(units) != expected:
            raise ValidationError({
                "serials": (
                    f'{line.menu_item.name} needs {expected} assigned '
                    f'{line.menu_item.get_serial_identifier_type_display().lower()}'
                    f'{"s" if expected != 1 else ""} before final payment; {len(units)} assigned.'
                )
            })
        assignments[line.pk] = units
    return assignments


@transaction.atomic
def execute_serialized_transfer(
    *,
    tenant_id,
    membership,
    from_outlet,
    to_outlet,
    serial_numbers,
    user,
    note="",
):
    from .models import StockBalance, StockMovement, StockReason
    import uuid

    if from_outlet.pk == to_outlet.pk:
        raise ValidationError({"to_outlet": "Destination must differ from source."})
    if from_outlet.site.tenant_id != tenant_id or to_outlet.site.tenant_id != tenant_id:
        raise ValidationError({"outlet": "Both sections must belong to this business."})
    if not outlet_belongs_to_membership(membership, from_outlet.pk):
        raise ValidationError({"from_outlet": "You cannot transfer from this section."})
    if not outlet_belongs_to_membership(membership, to_outlet.pk):
        raise ValidationError({"to_outlet": "You cannot transfer to this section."})

    identifiers = normalize_serial_numbers(serial_numbers)
    if not identifiers:
        raise ValidationError({"serial_numbers": "Enter at least one serial / IMEI to transfer."})

    units = []
    seen_ids = set()
    for identifier in identifiers:
        unit = (
            InventorySerialUnit.objects.select_for_update()
            .select_related("menu_item")
            .filter(
                tenant_id=tenant_id,
                outlet=from_outlet,
                serial_number__iexact=identifier,
                status__in=[SerializedUnitStatus.AVAILABLE, SerializedUnitStatus.RETURNED],
                reserved_order_line__isnull=True,
            )
            .first()
        )
        if unit is None:
            raise ValidationError({
                "serial_numbers": (
                    f'"{identifier}" is not an available serialized unit in {from_outlet.name}.'
                )
            })
        if not unit.menu_item.serial_tracking or not unit.menu_item.track_inventory:
            raise ValidationError({"serial_numbers": f'"{identifier}" has invalid serialized product configuration.'})
        if unit.pk in seen_ids:
            raise ValidationError({"serial_numbers": f'Duplicate serialized unit "{identifier}".'})
        seen_ids.add(unit.pk)
        units.append(unit)

    counts = {}
    names = {}
    for unit in units:
        counts[unit.menu_item_id] = counts.get(unit.menu_item_id, Decimal("0")) + Decimal("1")
        names[unit.menu_item_id] = unit.menu_item.name

    source_balances = {}
    destination_balances = {}
    for item_id in sorted(counts, key=str):
        source, _ = StockBalance.objects.select_for_update().get_or_create(
            tenant_id=tenant_id,
            outlet=from_outlet,
            menu_item_id=item_id,
            defaults={"quantity": Decimal("0")},
        )
        destination, _ = StockBalance.objects.select_for_update().get_or_create(
            tenant_id=tenant_id,
            outlet=to_outlet,
            menu_item_id=item_id,
            defaults={"quantity": Decimal("0")},
        )
        needed = counts[item_id]
        if source.quantity < needed:
            raise ValidationError({
                "stock": (
                    f'Aggregate stock for "{names[item_id]}" is below the serialized units selected '
                    f"(have {source.quantity}, need {needed}). Reconcile before transferring."
                )
            })
        if destination.quantity + needed > Decimal("99999999999.999"):
            raise ValidationError({"stock": f'Destination stock limit would be exceeded for "{names[item_id]}".'})
        source_balances[item_id] = source
        destination_balances[item_id] = destination

    transfer_batch = uuid.uuid4()
    note_text = (note or "").strip()[:400]
    for item_id in sorted(counts, key=str):
        qty = counts[item_id]
        source = source_balances[item_id]
        destination = destination_balances[item_id]
        source.quantity -= qty
        destination.quantity += qty
        source.save(update_fields=["quantity", "updated_at"])
        destination.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            tenant_id=tenant_id,
            outlet=from_outlet,
            menu_item_id=item_id,
            quantity_change=-qty,
            reason=StockReason.TRANSFER_OUT,
            transfer_batch=transfer_batch,
            created_by=user,
            note=(f"Serialized transfer to {to_outlet.name}. {note_text}")[:512],
        )
        StockMovement.objects.create(
            tenant_id=tenant_id,
            outlet=to_outlet,
            menu_item_id=item_id,
            quantity_change=qty,
            reason=StockReason.TRANSFER_IN,
            transfer_batch=transfer_batch,
            created_by=user,
            note=(f"Serialized transfer from {from_outlet.name}. {note_text}")[:512],
        )

    for unit in units:
        old_outlet = unit.outlet
        unit.outlet = to_outlet
        unit.save(update_fields=["outlet", "updated_at"])
        InventorySerialEvent.objects.create(
            tenant_id=tenant_id,
            serial_unit=unit,
            event_type=SerializedUnitEventType.TRANSFERRED,
            outlet=to_outlet,
            created_by=user,
            note=(
                f"Transferred from {old_outlet.name} to {to_outlet.name}"
                + (f" · {note_text}" if note_text else "")
            )[:512],
        )

    log_audit(
        tenant_id=tenant_id,
        user_id=user.pk if user else None,
        action="inventory.serials_transferred",
        entity_type="serialized_transfer",
        entity_id=str(transfer_batch),
        payload={
            "from_outlet_id": str(from_outlet.pk),
            "to_outlet_id": str(to_outlet.pk),
            "serial_unit_ids": [str(unit.pk) for unit in units],
            "counts": {str(item_id): str(qty) for item_id, qty in counts.items()},
        },
    )
    return transfer_batch, units


def lock_serial_units_for_return(*, order, order_line, quantity, serial_numbers) -> list[InventorySerialUnit]:
    serials = normalize_serial_numbers(serial_numbers)
    item = order_line.menu_item
    if item is None or not item.serial_tracking:
        if serials:
            raise ValidationError({"serial_numbers": "Serial / IMEI values are only valid for serialized products."})
        return []
    qty = Decimal(str(quantity))
    if qty != qty.to_integral_value():
        raise ValidationError({"serial_numbers": "Serialized returns use whole-unit quantities."})
    expected = int(qty)
    if len(serials) != expected:
        raise ValidationError({
            "serial_numbers": (
                f"Enter exactly {expected} returned {item.get_serial_identifier_type_display().lower()}"
                f'{"s" if expected != 1 else ""}.'
            )
        })
    units = []
    for identifier in serials:
        unit = (
            InventorySerialUnit.objects.select_for_update()
            .filter(
                tenant_id=order.tenant_id,
                outlet_id=order.outlet_id,
                menu_item=item,
                sold_order_line=order_line,
                status=SerializedUnitStatus.SOLD,
                serial_number__iexact=identifier,
            )
            .first()
        )
        if unit is None:
            raise ValidationError({
                "serial_numbers": (
                    f'"{identifier}" is not a sold serial / IMEI from this sale line '
                    "or it has already been returned."
                )
            })
        units.append(unit)
    return units


def complete_serialized_return(*, return_record, units, restock: bool, user) -> None:
    if not units:
        return
    from .services import apply_manual_stock_change

    order = return_record.order
    line = return_record.order_line
    quantity = Decimal(len(units))
    if restock:
        apply_manual_stock_change(
            tenant_id=order.tenant_id,
            outlet=order.outlet,
            menu_item=line.menu_item,
            quantity_change=quantity,
            reason="adjust_in",
            user=user,
            note=f"Serialized return {order.bill_reference}"[:512],
            allow_serialized=True,
        )
    disposition = (
        InventorySerialReturnLink.Disposition.RESTOCKED
        if restock
        else InventorySerialReturnLink.Disposition.QUARANTINED
    )
    event_type = (
        SerializedUnitEventType.RETURNED
        if restock
        else SerializedUnitEventType.QUARANTINED
    )
    status = (
        SerializedUnitStatus.RETURNED
        if restock
        else SerializedUnitStatus.QUARANTINED
    )
    for unit in units:
        unit.status = status
        unit.reserved_order_line = None
        unit.save(update_fields=["status", "reserved_order_line", "updated_at"])
        InventorySerialReturnLink.objects.create(
            tenant_id=order.tenant_id,
            serial_unit=unit,
            return_record=return_record,
            disposition=disposition,
        )
        InventorySerialEvent.objects.create(
            tenant_id=order.tenant_id,
            serial_unit=unit,
            event_type=event_type,
            outlet=order.outlet,
            order_line=line,
            created_by=user,
            note=(
                f"Returned on {order.bill_reference}; "
                + ("restocked for resale" if restock else "quarantined / not restocked")
            )[:512],
        )
    log_audit(
        tenant_id=order.tenant_id,
        user_id=user.pk if user else None,
        action="inventory.serials_returned",
        entity_type="supermarket_line_return",
        entity_id=str(return_record.pk),
        payload={
            "order_id": str(order.pk),
            "order_line_id": str(line.pk),
            "restock": restock,
            "serial_unit_ids": [str(unit.pk) for unit in units],
        },
    )


def mark_serial_assignments_sold(*, order, assignments: dict, user) -> None:
    now = timezone.now()
    sold_date = timezone.localdate(now)
    for line_id, units in assignments.items():
        line = order.lines.get(pk=line_id)
        for unit in units:
            unit.status = SerializedUnitStatus.SOLD
            unit.sold_order_line = line
            unit.reserved_order_line = None
            unit.sold_at = now
            unit.warranty_started_at = sold_date if line.menu_item.warranty_months else None
            unit.warranty_expires_at = _add_months(
                sold_date, line.menu_item.warranty_months
            )
            unit.save(update_fields=[
                "status", "sold_order_line", "reserved_order_line", "sold_at",
                "warranty_started_at", "warranty_expires_at", "updated_at"
            ])
            InventorySerialEvent.objects.create(
                tenant_id=order.tenant_id,
                serial_unit=unit,
                event_type=SerializedUnitEventType.SOLD,
                outlet=order.outlet,
                order_line=line,
                created_by=user,
                note=f"Sold on {order.bill_reference}"[:512],
            )
