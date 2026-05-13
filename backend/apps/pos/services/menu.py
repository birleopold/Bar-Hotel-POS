from django.db.models import Count, Q

from apps.catalog.models import MenuItem


def menu_item_available_at_outlet(menu_item: MenuItem, outlet_id) -> bool:
    if not menu_item.outlet_links.exists():
        return True
    return menu_item.outlet_links.filter(outlet_id=outlet_id).exists()


def menu_items_for_outlet_queryset(tenant_id, outlet_id):
    qs = (
        MenuItem.objects.filter(tenant_id=tenant_id, is_active=True)
        .select_related("category")
        .annotate(outlet_link_count=Count("outlet_links", distinct=True))
        .filter(Q(outlet_link_count=0) | Q(outlet_links__outlet_id=outlet_id))
        .distinct()
    )
    return qs
