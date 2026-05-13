"""Outlet-scoped catalog fingerprint for offline POS cache invalidation."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemOutlet,
    ModifierGroup,
    ModifierOption,
    Promotion,
    SupermarketSkuProfile,
)
from apps.pos.services.menu import menu_items_for_outlet_queryset


def catalog_version_payload(*, tenant_id: uuid.UUID, outlet_id: uuid.UUID) -> dict[str, Any]:
    """
    Return a stable token and timestamp for If-None-Match style client pinning.

    Incorporates categories, sellable items at outlet, outlet price overrides, promotions,
    and supermarket SKU profile changes for the tenant.
    """
    cat_max = MenuCategory.objects.filter(tenant_id=tenant_id).aggregate(m=Max("updated_at"))["m"]
    items_qs = menu_items_for_outlet_queryset(tenant_id, outlet_id)
    item_agg = items_qs.aggregate(m=Max("updated_at"), c=Count("id", distinct=True))
    item_max = item_agg["m"]
    item_count = item_agg["c"] or 0

    promos = (
        Promotion.objects.filter(tenant_id=tenant_id)
        .annotate(n=Count("outlets"))
        .filter(Q(n=0) | Q(outlets=outlet_id))
        .distinct()
    )
    promo_max = promos.aggregate(m=Max("updated_at"))["m"]

    links = MenuItemOutlet.objects.filter(outlet_id=outlet_id).order_by("menu_item_id").values_list(
        "menu_item_id",
        "price_override",
    )
    link_blob = ",".join(f"{mid}:{(po or '')}" for mid, po in links)

    sku_max = SupermarketSkuProfile.objects.filter(tenant_id=tenant_id).aggregate(m=Max("updated_at"))["m"]
    mod_g_max = ModifierGroup.objects.filter(tenant_id=tenant_id).aggregate(m=Max("updated_at"))["m"]
    mod_o_max = ModifierOption.objects.filter(group__tenant_id=tenant_id).aggregate(m=Max("updated_at"))["m"]
    mod_links = MenuItemModifierGroup.objects.filter(menu_item__tenant_id=tenant_id).values_list(
        "menu_item_id",
        "group_id",
        "sort_order",
    )
    mod_link_blob = ",".join(f"{mid}:{gid}:{so}" for mid, gid, so in sorted(mod_links))

    parts = [
        str(tenant_id),
        str(outlet_id),
        cat_max.isoformat() if cat_max else "",
        item_max.isoformat() if item_max else "",
        str(item_count),
        promo_max.isoformat() if promo_max else "",
        link_blob,
        sku_max.isoformat() if sku_max else "",
        mod_g_max.isoformat() if mod_g_max else "",
        mod_o_max.isoformat() if mod_o_max else "",
        mod_link_blob,
    ]
    raw = "|".join(parts)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:32]

    candidates = [
        t for t in (cat_max, item_max, promo_max, sku_max, mod_g_max, mod_o_max) if t is not None
    ]
    max_ts = max(candidates) if candidates else timezone.now()

    return {
        "catalog_version": digest,
        "as_of": max_ts.isoformat(),
    }
