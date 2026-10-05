from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.pos.models import Order, OrderLine, OrderStatus


@transaction.atomic
def update_order_line_kds_status(
    *,
    order: Order,
    line: OrderLine,
    kds_status: str,
    kds_station: str | None,
    user,
) -> OrderLine:
    from apps.pos.models import KdsLineStatus

    if kds_status not in {c.value for c in KdsLineStatus}:
        raise ValidationError({"kds_status": "Invalid status."})

    locked_o = Order.objects.select_for_update().get(pk=order.pk)
    if locked_o.status != OrderStatus.OPEN:
        raise ValidationError("Kitchen line status can only change on open orders.")
    ln = OrderLine.objects.select_for_update().get(pk=line.pk, order_id=locked_o.id)
    if ln.is_voided:
        raise ValidationError("Voided lines cannot be updated on KDS.")
    allowed_next = {
        KdsLineStatus.PENDING.value: KdsLineStatus.IN_PREP.value,
        KdsLineStatus.IN_PREP.value: KdsLineStatus.READY.value,
        KdsLineStatus.READY.value: KdsLineStatus.SERVED.value,
    }
    if allowed_next.get(ln.kds_status) != kds_status:
        raise ValidationError({"kds_status": "Prep status must advance one step at a time."})
    ln.kds_status = kds_status
    if kds_station is not None:
        ln.kds_station = (kds_station or "")[:32]
    ln.save(update_fields=["kds_status", "kds_station", "updated_at"])
    log_audit(
        tenant_id=locked_o.tenant_id,
        user_id=user.id if user else None,
        action="order.kds_line_updated",
        entity_type="order_line",
        entity_id=str(ln.id),
        payload={"kds_status": kds_status, "order_id": str(locked_o.id)},
    )
    return ln
