from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.catalog.models import MenuCategory, MenuItem, MenuItemOutlet
from apps.pos.menu_cache import invalidate_menu_cache_for_tenant


@receiver([post_save, post_delete], sender=MenuItem)
def _invalidate_menu_cache_menu_item(sender, instance, **kwargs):
    invalidate_menu_cache_for_tenant(instance.tenant_id)


@receiver([post_save, post_delete], sender=MenuCategory)
def _invalidate_menu_cache_category(sender, instance, **kwargs):
    invalidate_menu_cache_for_tenant(instance.tenant_id)


@receiver([post_save, post_delete], sender=MenuItemOutlet)
def _invalidate_menu_cache_item_outlet(sender, instance, **kwargs):
    invalidate_menu_cache_for_tenant(instance.menu_item.tenant_id)
