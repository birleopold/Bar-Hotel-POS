"""Tenant-scoped supermarket shelf locator; location labels are not stock quantities."""
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.audit.services import log_audit
from apps.catalog.models import MenuItem
from apps.tenants.models import Outlet
from .models import StockShelfLocation


@transaction.atomic
def set_stock_shelf_location(*, tenant_id, outlet_id, menu_item_id, aisle="", shelf="",
                             bin_code="", note="", membership, user=None):
    from apps.staff.services.permissions import membership_has_inventory_capability
    try:
        outlet_id = UUID(str(outlet_id))
        menu_item_id = UUID(str(menu_item_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError({"detail": "Select a valid product and store section."}) from exc
    if not membership_has_inventory_capability(membership, "adjust"):
        raise ValidationError({"detail": "Your role cannot change shelf locations."})
    if not outlet_belongs_to_membership(membership, outlet_id):
        raise ValidationError({"outlet": "Select an authorized section."})
    outlet = Outlet.objects.filter(pk=outlet_id, site__tenant_id=tenant_id, is_active=True).first()
    item = MenuItem.objects.filter(pk=menu_item_id, tenant_id=tenant_id, track_inventory=True).first()
    if outlet is None or item is None:
        raise ValidationError({"detail": "Select a tracked item and section from this business."})
    values = {}
    for key, raw, limit in (
        ("aisle", aisle, 32), ("shelf", shelf, 32), ("bin_code", bin_code, 32),
        ("note", note, 160),
    ):
        if not isinstance(raw, str) or len(raw.strip()) > limit:
            raise ValidationError({key: "Enter a short location label within the allowed length."})
        values[key] = raw.strip()
    if not any(values[k] for k in ("aisle", "shelf", "bin_code")):
        raise ValidationError({"location": "Enter an aisle, shelf or bin to make this item findable."})
    existing = StockShelfLocation.objects.select_for_update().filter(
        tenant_id=tenant_id, outlet=outlet, menu_item=item,
    ).first()
    if existing is not None:
        changed = {k: [getattr(existing, k), value] for k, value in values.items()
                   if getattr(existing, k) != value}
        if not changed:
            return existing, True
        before = {key: old for key, (old, _) in changed.items()}
        for key, value in values.items():
            setattr(existing, key, value)
        existing.updated_by = user
        existing.save(update_fields=[*values, "updated_by", "updated_at"])
        location = existing
    else:
        before = {}
        location = StockShelfLocation.objects.create(
            tenant_id=tenant_id, outlet=outlet, menu_item=item,
            updated_by=user, **values,
        )
    log_audit(
        tenant_id=tenant_id, user_id=user.pk if user else None,
        action="stock.shelf_location_saved",
        entity_type="stock_shelf_location", entity_id=str(location.pk),
        payload={"outlet_id": str(outlet.id), "menu_item_id": str(item.id),
                 "previous": before, "new": values,
                 "stock_quantity_changed": False},
    )
    return location, False
