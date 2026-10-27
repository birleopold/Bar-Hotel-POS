"""Tenant-safe product label queue built on the existing shelf-label workflow."""
from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.tenants.models import Outlet, OutletType

from .models import MenuItem, ProductLabelQueueEntry


RETAIL_OUTLET_TYPES = {OutletType.RETAIL, OutletType.SUPERMARKET}


def retail_label_outlets_for_item(*, item: MenuItem) -> list[Outlet]:
    """Return active retail outlets where the product is configured to sell."""
    explicit_ids = list(item.outlet_links.values_list("outlet_id", flat=True))
    qs = Outlet.objects.filter(
        site__tenant_id=item.tenant_id,
        is_active=True,
        outlet_type__in=RETAIL_OUTLET_TYPES,
    )
    if explicit_ids:
        qs = qs.filter(pk__in=explicit_ids)
    return list(qs.select_related("site").order_by("site__name", "name"))


@transaction.atomic
def queue_product_label(
    *,
    tenant_id,
    outlet: Outlet,
    menu_item: MenuItem,
    reason: str,
    user=None,
    note: str = "",
) -> ProductLabelQueueEntry | None:
    """Create/update one pending label task without creating duplicate work."""
    if reason not in ProductLabelQueueEntry.Reason.values:
        raise ValidationError({"reason": "Choose a supported label reason."})
    if outlet.site.tenant_id != tenant_id or menu_item.tenant_id != tenant_id:
        raise ValidationError({"label": "Label outlet and product must belong to this business."})
    if outlet.outlet_type not in RETAIL_OUTLET_TYPES or not outlet.is_active:
        return None

    price = menu_item.unit_price_for_outlet(outlet.pk)
    entry, created = ProductLabelQueueEntry.objects.update_or_create(
        tenant_id=tenant_id,
        outlet=outlet,
        menu_item=menu_item,
        reason=reason,
        status=ProductLabelQueueEntry.Status.PENDING,
        defaults={
            "price_snapshot": price,
            "note": (note or "")[:255],
            "requested_by": user,
            "completed_by": None,
            "completed_at": None,
        },
    )
    if not created:
        entry.price_snapshot = price
        entry.note = (note or "")[:255]
        entry.requested_by = user
        entry.completed_by = None
        entry.completed_at = None
        entry.save(update_fields=[
            "price_snapshot", "note", "requested_by",
            "completed_by", "completed_at", "updated_at",
        ])
    return entry


@transaction.atomic
def queue_product_labels(
    *,
    menu_item: MenuItem,
    reason: str,
    user=None,
    outlets: Iterable[Outlet] | None = None,
    note: str = "",
) -> int:
    targets = list(outlets) if outlets is not None else retail_label_outlets_for_item(item=menu_item)
    count = 0
    for outlet in targets:
        if queue_product_label(
            tenant_id=menu_item.tenant_id,
            outlet=outlet,
            menu_item=menu_item,
            reason=reason,
            user=user,
            note=note,
        ) is not None:
            count += 1
    return count


@transaction.atomic
def dismiss_product_label_entries(
    *,
    tenant_id,
    outlet: Outlet,
    entry_ids,
    user=None,
    note: str = "",
) -> int:
    """Dismiss pending label tasks without pretending they were printed."""
    if outlet.site.tenant_id != tenant_id:
        raise ValidationError({"outlet": "Label outlet must belong to this business."})
    ids = list(dict.fromkeys(entry_ids))
    if not ids:
        return 0
    now = timezone.now()
    qs = ProductLabelQueueEntry.objects.select_for_update().filter(
        tenant_id=tenant_id,
        outlet=outlet,
        pk__in=ids,
        status=ProductLabelQueueEntry.Status.PENDING,
    )
    entries = list(qs.select_related("menu_item"))
    if not entries:
        return 0
    for entry in entries:
        entry.status = ProductLabelQueueEntry.Status.DISMISSED
        entry.completed_by = user
        entry.completed_at = now
        if note:
            entry.note = (note or "")[:255]
        entry.save(update_fields=[
            "status", "completed_by", "completed_at", "note", "updated_at",
        ])
    log_audit(
        tenant_id=tenant_id,
        user_id=user.pk if user else None,
        action="catalog.product_labels_dismissed",
        entity_type="product_label_queue",
        entity_id=str(outlet.pk),
        payload={
            "outlet_id": str(outlet.pk),
            "entry_ids": [str(entry.pk) for entry in entries],
            "item_ids": [str(entry.menu_item_id) for entry in entries],
            "count": len(entries),
            "note": (note or "")[:255],
        },
    )
    return len(entries)


@transaction.atomic
def mark_product_labels_printed(
    *,
    tenant_id,
    outlet: Outlet,
    menu_item_ids,
    user=None,
) -> int:
    if outlet.site.tenant_id != tenant_id:
        raise ValidationError({"outlet": "Label outlet must belong to this business."})
    ids = list(dict.fromkeys(menu_item_ids))
    if not ids:
        return 0
    now = timezone.now()
    qs = ProductLabelQueueEntry.objects.select_for_update().filter(
        tenant_id=tenant_id,
        outlet=outlet,
        menu_item_id__in=ids,
        status=ProductLabelQueueEntry.Status.PENDING,
    )
    entry_ids = list(qs.values_list("id", flat=True))
    if not entry_ids:
        return 0
    changed = ProductLabelQueueEntry.objects.filter(pk__in=entry_ids).update(
        status=ProductLabelQueueEntry.Status.PRINTED,
        completed_by=user,
        completed_at=now,
        updated_at=now,
    )
    log_audit(
        tenant_id=tenant_id,
        user_id=user.pk if user else None,
        action="catalog.product_labels_printed",
        entity_type="product_label_queue",
        entity_id=str(outlet.pk),
        payload={
            "outlet_id": str(outlet.pk),
            "item_ids": [str(value) for value in ids],
            "queue_entries_completed": changed,
        },
    )
    return changed
