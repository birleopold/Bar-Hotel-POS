"""Keep ``MenuItem`` ↔ outlet through rows in sync with the item form without losing ``price_override``."""

from __future__ import annotations

from apps.catalog.models import MenuItem, MenuItemModifierGroup, MenuItemOutlet


def sync_menu_item_outlet_links(menu_item: MenuItem, selected_outlets) -> None:
    """
    Empty selection → item is offered at every outlet (no through rows).
    Non-empty → one row per outlet; existing rows keep their ``price_override``.
    """
    selected_ids = {o.id for o in (selected_outlets or [])}
    if not selected_ids:
        MenuItemOutlet.objects.filter(menu_item=menu_item).delete()
        return
    for oid in selected_ids:
        MenuItemOutlet.objects.get_or_create(
            menu_item=menu_item,
            outlet_id=oid,
            defaults={"price_override": None},
        )
    MenuItemOutlet.objects.filter(menu_item=menu_item).exclude(outlet_id__in=selected_ids).delete()


def sync_menu_item_modifier_groups(menu_item: MenuItem, selected_groups) -> None:
    """Replace modifier group links; order follows the iterable (form multi-select order)."""
    groups = list(selected_groups or [])
    MenuItemModifierGroup.objects.filter(menu_item=menu_item).delete()
    for i, g in enumerate(groups):
        MenuItemModifierGroup.objects.create(menu_item=menu_item, group=g, sort_order=i)
