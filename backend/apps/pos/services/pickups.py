"""No-inventory-repost collection workflow for already fully paid retail orders.

A paid pickup is NOT layaway, an unpaid reservation or a customer debt.
"""
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.audit.services import log_audit
from apps.pos.models import Order, OrderStatus, RetailPickup
from apps.pos.services.wholesale import manager_allowed
from apps.staff.services.permissions import membership_can_modify_lodging
from apps.access.outlets import outlet_belongs_to_membership
from apps.tenants.models import OutletType


@transaction.atomic
def register_paid_pickup(*, order, expected_on, note, user, membership):
    locked = Order.objects.select_for_update().select_related("outlet").get(pk=order.pk)
    if (locked.outlet.outlet_type not in {OutletType.RETAIL, OutletType.SUPERMARKET}
            or not manager_allowed(membership, locked.tenant_id, locked.outlet_id)
            or membership.user_id != user.pk):
        raise ValidationError({"detail": "An authorized retail manager must register pickup."})
    from django.db.models import Sum
    from apps.pos.models import Payment
    paid = Payment.objects.filter(order=locked, tenant_id=locked.tenant_id).aggregate(v=Sum("amount"))["v"] or 0
    if paid < locked.total:
        raise ValidationError({"order": "Confirm the real recorded payment before scheduling pickup."})
    if not locked.is_paid or locked.status != OrderStatus.CLOSED or not locked.customer_id:
        raise ValidationError({"order": "Pickup requires a fully paid sale linked to an identified customer."})
    if locked.refunds.exists():
        raise ValidationError({"order": "Refunded sale needs manager review before scheduling pickup."})
    if not isinstance(expected_on, date) or isinstance(expected_on, __import__("datetime").datetime):
        raise ValidationError({"expected_on": "Enter a pickup date."})
    if not timezone.localdate() <= expected_on <= timezone.localdate() + timedelta(days=365):
        raise ValidationError({"expected_on": "Choose a date within the next year."})
    note = (note or "").strip()
    if len(note) > 300:
        raise ValidationError({"note": "Use at most 300 characters."})
    existing = RetailPickup.objects.filter(order=locked, tenant_id=locked.tenant_id).first()
    if existing:
        if existing.expected_on == expected_on and existing.note == note:
            return existing, True
        raise ValidationError({"order": "Pickup was already recorded; do not overwrite a confirmed collection."})
    pickup = RetailPickup.objects.create(
        tenant_id=locked.tenant_id, order=locked,
        expected_on=expected_on, note=note, created_by=user,
    )
    log_audit(tenant_id=locked.tenant_id, user_id=user.pk,
              action="retail.pickup_scheduled", entity_type="retail_pickup",
              entity_id=str(pickup.pk), payload={
                  "order_id": str(locked.pk), "expected_on": expected_on.isoformat(),
                  "stock_deducted_again": False,
              })
    return pickup, False


@transaction.atomic
def hand_over_paid_pickup(*, pickup, note, user, membership):
    locked = Order.objects.select_for_update().select_related("outlet").get(pk=pickup.order_id)
    row = RetailPickup.objects.select_for_update().filter(
        pk=pickup.pk, tenant_id=locked.tenant_id, order=locked,
    ).first()
    if row is None:
        raise ValidationError({"detail": "Pickup no longer available."})
    if (not membership or not membership.is_active or membership.user_id != user.pk
            or membership.tenant_id != locked.tenant_id
            or not membership_can_modify_lodging(membership)
            or not outlet_belongs_to_membership(membership, locked.outlet_id)):
        raise ValidationError({"detail": "Only staff authorized for this retail section may confirm handover."})
    if row.status == RetailPickup.Status.COLLECTED:
        return row, True
    if not locked.is_paid or locked.status != OrderStatus.CLOSED or locked.refunds.exists():
        raise ValidationError({"order": "Refunded or unpaid orders need manager review before pickup."})
    note = (note or "").strip()
    if not 12 <= len(note) <= 300:
        raise ValidationError({"note": "Record an identity and physical handover note (12–300 characters)."})
    row.status = RetailPickup.Status.COLLECTED
    row.collected_by = user
    row.collected_at = timezone.now()
    row.note = (row.note + " | Handover: " + note)[:300]
    row.save(update_fields=["status", "collected_by", "collected_at", "note", "updated_at"])
    log_audit(tenant_id=locked.tenant_id, user_id=user.pk,
              action="retail.pickup_collected", entity_type="retail_pickup",
              entity_id=str(row.pk), payload={
                  "order_id": str(locked.pk), "picked_up_at": row.collected_at.isoformat(),
                  "handover_note": note, "additional_stock_posted": False,
              })
    return row, False
