"""Explicitly configured EAN-13 variable-weight labels.

Layout is opt-in: PP (20-29) + IIIII (store item code) + GGGGG
(weight in grams) + EAN-13 check digit. National/supplier label layouts
differ; the application never interprets arbitrary 20-29 barcodes as weight.
"""
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from .models import MenuItem, SupermarketSkuProfile, UnitOfMeasure, WeightedPricingMode


def ean13_check_digit(first_twelve: str) -> str:
    if not isinstance(first_twelve, str) or len(first_twelve) != 12 or not first_twelve.isascii() or not first_twelve.isdecimal():
        raise ValueError("EAN-13 needs twelve ASCII digits.")
    value = sum(int(ch) * (3 if i % 2 else 1) for i, ch in enumerate(first_twelve))
    return str((-value) % 10)


def make_scale_weight_label(*, prefix: str, item_code: str, grams: int) -> str:
    if (not isinstance(grams, int) or not 1 <= grams <= 99999
            or not isinstance(prefix, str) or not prefix.isascii() or prefix not in [str(x) for x in range(20, 30)]
            or not isinstance(item_code, str) or len(item_code) != 5
            or not item_code.isascii() or not item_code.isdecimal()):
        raise ValueError("Use a configured 20–29 prefix, five-digit product and 1–99999 grams.")
    body = f"{prefix}{item_code}{grams:05d}"
    return body + ean13_check_digit(body)


@transaction.atomic
def configure_scale_weight_label(*, tenant_id, menu_item_id, prefix, item_code, membership, user):
    from apps.staff.services.permissions import membership_can_manage_workspace_settings

    if (membership is None or not membership.is_active
            or membership.tenant_id != tenant_id
            or not membership_can_manage_workspace_settings(membership)):
        raise ValidationError({"detail": "Only an active business owner or administrator can configure scale labels."})
    try:
        menu_item_id = UUID(str(menu_item_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError({"menu_item_id": "Select a valid kilogram product."}) from exc
    item = MenuItem.objects.filter(
        pk=menu_item_id, tenant_id=tenant_id, unit_of_measure=UnitOfMeasure.KG,
        track_inventory=True, is_active=True,
    ).first()
    if item is None:
        raise ValidationError({"menu_item_id": "Only active, stock-tracked kilogram products can use weighed labels."})
    from apps.access.outlets import membership_outlet_ids
    from apps.pos.services.menu import menu_item_available_at_outlet
    if not any(menu_item_available_at_outlet(item, oid) for oid in membership_outlet_ids(membership)):
        raise ValidationError({"menu_item_id": "This product is outside your authorized store sections."})
    prefix = str(prefix or "").strip()
    item_code = str(item_code or "").strip()
    if bool(prefix) != bool(item_code):
        raise ValidationError({"scale_code": "Enter both a two-digit prefix and five-digit item code, or clear both."})
    if prefix and (prefix not in [str(v) for v in range(20, 30)]
                   or len(item_code) != 5 or not item_code.isascii() or not item_code.isdecimal()):
        raise ValidationError({"scale_code": "Use a locally configured prefix 20–29 and an exact five-digit item code."})
    conflict = SupermarketSkuProfile.objects.filter(
        tenant_id=tenant_id, scale_prefix=prefix, scale_item_code=item_code,
    ).exclude(menu_item=item).exists() if prefix else False
    if conflict:
        raise ValidationError({"scale_code": "This scale product code is already assigned to another item."})
    profile, created = SupermarketSkuProfile.objects.select_for_update().get_or_create(
        tenant_id=tenant_id, menu_item=item,
    )
    if not created and (profile.scale_prefix, profile.scale_item_code) == (prefix, item_code):
        return profile, True
    before = {"prefix": profile.scale_prefix, "item_code": profile.scale_item_code}
    profile.scale_prefix = prefix
    profile.scale_item_code = item_code
    if prefix:
        profile.weighted_pricing_mode = WeightedPricingMode.WEIGHTED
        profile.allow_fractional_quantity = True
        profile.sell_by_unit = False
        profile.is_active = True
    profile.save(update_fields=[
        "scale_prefix", "scale_item_code", "weighted_pricing_mode",
        "allow_fractional_quantity", "sell_by_unit", "is_active", "updated_at",
    ])
    log_audit(
        tenant_id=tenant_id, user_id=user.pk if user else None,
        action="catalog.scale_label_configured", entity_type="supermarket_sku_profile",
        entity_id=str(profile.pk), payload={
            "menu_item_id": str(item.pk), "before": before,
            "after": {"prefix": prefix, "item_code": item_code},
            "unit_price_changed": False, "stock_changed": False,
        },
    )
    return profile, False


def decode_scale_weight_label(*, tenant_id, outlet_id, code):
    """Returns (item, kg quantity), None if no configured format matches.

    A label for a *known* prefix/product combination with a bad checksum
    is rejected instead of falling through to a misleading ordinary barcode.
    """
    if not isinstance(code, str) or len(code) != 13 or not code.isascii() or not code.isdecimal():
        return None
    profile = SupermarketSkuProfile.objects.select_related("menu_item").filter(
        tenant_id=tenant_id,
        is_active=True, menu_item__is_active=True,
        scale_prefix=code[:2], scale_item_code=code[2:7],
    ).first()
    if profile is None:
        return None
    from apps.tenants.models import Outlet, OutletType
    if not Outlet.objects.filter(
        pk=outlet_id, site__tenant_id=tenant_id, is_active=True,
        outlet_type__in=[OutletType.RETAIL, OutletType.SUPERMARKET],
    ).exists():
        raise ValidationError({"code": "Scale labels may only be scanned at an authorized retail outlet."})
    item = profile.menu_item
    if (profile.weighted_pricing_mode != WeightedPricingMode.WEIGHTED
            or not profile.allow_fractional_quantity or item.unit_of_measure != UnitOfMeasure.KG):
        raise ValidationError({"code": "Scale label configuration for this product is incomplete."})
    from apps.pos.services.menu import menu_item_available_at_outlet
    if not menu_item_available_at_outlet(item, outlet_id):
        raise ValidationError({"code": "The weighed item is not available in this section."})
    if code[-1] != ean13_check_digit(code[:12]):
        raise ValidationError({"code": "Invalid scale label checksum; weigh and print a new label."})
    grams = int(code[7:12])
    if grams <= 0:
        raise ValidationError({"code": "Scale label must contain a positive net weight."})
    return item, Decimal(grams) / Decimal("1000")
