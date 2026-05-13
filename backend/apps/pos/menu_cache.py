"""Short-TTL cache of menu item PK lists per tenant/outlet (API list); invalidated on catalog changes."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db.models import Case, IntegerField, Prefetch, When

from apps.catalog.models import MenuItem, MenuItemOutlet
from apps.tenants.models import Outlet

from .services import menu_items_for_outlet_queryset


def menu_cache_key(tenant_id, outlet_id) -> str:
    return f"pos:menu_pks:{tenant_id}:{outlet_id}"


def invalidate_menu_cache_for_tenant(tenant_id) -> None:
    prefix = f"pos:menu_pks:{tenant_id}:"
    client = getattr(cache, "delete_pattern", None)
    if callable(client):
        cache.delete_pattern(f"{prefix}*")
        return
    for oid in Outlet.objects.filter(site__tenant_id=tenant_id).values_list("id", flat=True):
        cache.delete(menu_cache_key(tenant_id, oid))


def menu_items_for_outlet_queryset_cached(tenant_id, outlet_id):
    """
    Same rows/order as menu_items_for_outlet_queryset + default API ordering.
    Caches ordered PK list; use for high-traffic list endpoints only.
    """
    ttl = getattr(settings, "MENU_CACHE_TTL_SECONDS", 60)
    key = menu_cache_key(tenant_id, outlet_id)
    pks = cache.get(key)
    if pks is None:
        base = menu_items_for_outlet_queryset(tenant_id, outlet_id).order_by(
            "category__sort_order", "category__name", "name"
        )
        pks = list(base.values_list("pk", flat=True))
        cache.set(key, pks, ttl)
    if not pks:
        return MenuItem.objects.filter(tenant_id=tenant_id).none()
    whens = [When(pk=pk, then=pos) for pos, pk in enumerate(pks)]
    return (
        MenuItem.objects.filter(tenant_id=tenant_id, pk__in=pks)
        .select_related("category")
        .prefetch_related(
            Prefetch(
                "outlet_links",
                queryset=MenuItemOutlet.objects.filter(outlet_id=outlet_id),
            )
        )
        .annotate(_menu_ord=Case(*whens, output_field=IntegerField()))
        .order_by("_menu_ord")
    )
