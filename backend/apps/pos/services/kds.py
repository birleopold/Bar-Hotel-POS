from django.db import transaction
from django.utils import timezone
from apps.accounts.models import MembershipRole
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.pos.models import Order, OrderLine, OrderStatus


def kds_station_section(station: str) -> str:
    token = (station or "").strip().lower()
    if token in {"bar", "drinks", "beverage", "bartender"}:
        return "bar"
    if token in {"service", "spa", "steam", "sauna", "lodging", "frontdesk", "front_desk"}:
        return "service"
    return "kitchen"




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
    if not (locked_o.status == OrderStatus.OPEN or
            (locked_o.status == OrderStatus.CLOSED and locked_o.is_paid)):
        raise ValidationError("Only open or paid orders can continue through preparation.")
    ln = OrderLine.objects.select_for_update().get(pk=line.pk, order_id=locked_o.id)
    if ln.is_voided:
        raise ValidationError("Voided lines cannot be updated on KDS.")
    allowed_next = {
        KdsLineStatus.PENDING.value: (KdsLineStatus.ACCEPTED.value, KdsLineStatus.IN_PREP.value),
        KdsLineStatus.ACCEPTED.value: (KdsLineStatus.IN_PREP.value,),
        KdsLineStatus.IN_PREP.value: KdsLineStatus.READY.value,
        KdsLineStatus.READY.value: KdsLineStatus.SERVED.value,
    }
    accepted_next = allowed_next.get(ln.kds_status)
    if isinstance(accepted_next, str):
        accepted_next = (accepted_next,)
    if not accepted_next or kds_status not in accepted_next:
        raise ValidationError({"kds_status": "Prep status must advance one step at a time."})
    ln.kds_status = kds_status
    ln.kds_status_changed_at = timezone.now()
    if kds_station is not None:
        ln.kds_station = (kds_station or "")[:32]
    ln.save(update_fields=["kds_status", "kds_station", "kds_status_changed_at", "updated_at"])
    log_audit(
        tenant_id=locked_o.tenant_id,
        user_id=user.id if user else None,
        action="order.kds_line_updated",
        entity_type="order_line",
        entity_id=str(ln.id),
        payload={"kds_status": kds_status, "order_id": str(locked_o.id)},
    )
    return ln



@transaction.atomic
def manage_kds_item(*, order, line, membership, user, action, reason=""):
    """Manager-only rush/unrush and controlled recall of a ready item.

    Status is checked under an order and line lock so an outdated screen
    cannot override another cook's more recent update.
    """
    from apps.pos.models import KdsLineStatus
    from rest_framework.exceptions import ValidationError
    allowed_roles = {
        MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
        MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
    }
    if (not membership.is_active or membership.role not in allowed_roles
            or membership.tenant_id != order.tenant_id or membership.user_id != user.pk):
        raise ValidationError({"detail": "A manager must authorize a rush or recall."})
    locked = Order.objects.select_for_update().get(pk=order.pk, tenant_id=membership.tenant_id)
    if not (locked.status == OrderStatus.OPEN or
            (locked.status == OrderStatus.CLOSED and locked.is_paid)):
        raise ValidationError({"detail": "Only open or paid prep items can be changed."})
    ln = OrderLine.objects.select_for_update().get(pk=line.pk, order=locked)
    if ln.is_voided or ln.kds_status == KdsLineStatus.SERVED:
        raise ValidationError({"detail": "A voided or served item cannot be changed."})
    action = (action or "").strip()
    update = []
    if action in {"rush", "normal"}:
        urgent = action == "rush"
        if ln.kds_rush == urgent:
            return ln, False
        ln.kds_rush = urgent
        update.append("kds_rush")
    elif action == "recall":
        note = (reason or "").strip()
        if not note or len(note) > 255:
            raise ValidationError({"reason": "Explain why this ready item must be prepared again (up to 255 characters)."})
        if ln.kds_status != KdsLineStatus.READY:
            raise ValidationError({"detail": "Only ready items can be recalled to preparation."})
        ln.kds_status = KdsLineStatus.IN_PREP
        ln.kds_status_changed_at = timezone.now()
        update.extend(["kds_status", "kds_status_changed_at"])
    else:
        raise ValidationError({"action": "Choose rush, normal or recall."})
    ln.save(update_fields=[*update, "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id, user_id=user.pk,
        action="order.kds_item_managed", entity_type="order_line", entity_id=str(ln.pk),
        payload={
            "order_id": str(locked.pk), "action": action,
            "reason": (reason or "").strip()[:255],
            "priority": ln.kds_rush, "status": ln.kds_status,
        },
    )
    return ln, True
