from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.pos.models import OrderLine


def _kds_group_name(tenant_id, outlet_id) -> str:
    return f"kds_{tenant_id}_{outlet_id}"


@receiver(post_save, sender=OrderLine)
def _broadcast_kds_on_line_change(sender, instance: OrderLine, **kwargs):
    order = instance.order
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        _kds_group_name(order.tenant_id, order.outlet_id),
        {"type": "kds.notify", "event": "queue_changed"},
    )
