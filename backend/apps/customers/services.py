from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.customers.models import Customer
from apps.events.models import EventBooking
from apps.lodging.models import Folio, Reservation
from apps.pos.models import Order


@transaction.atomic
def merge_customers(*, source, target, tenant_id, user, reason):
    """Explicit same-tenant merge; retain the source identity and transaction snapshots."""
    reason = (reason or "").strip()
    if not reason or len(reason) > 512 or source.pk == target.pk:
        raise ValidationError("Choose a different customer and explain the merge (up to 512 characters).")
    ids = sorted([source.pk, target.pk])
    locked = {c.pk: c for c in Customer.objects.select_for_update().filter(tenant_id=tenant_id, pk__in=ids).order_by("pk")}
    if len(locked) != 2:
        raise ValidationError("Both customers must belong to this business.")
    src, dst = locked[source.pk], locked[target.pk]
    if src.merged_into_id or dst.merged_into_id:
        raise ValidationError("Choose two active customer records.")
    counts = {
        "reservations": Reservation.objects.filter(tenant_id=tenant_id, customer=src).update(customer=dst),
        "folios": Folio.objects.filter(tenant_id=tenant_id, customer=src).update(customer=dst),
        "orders": Order.objects.filter(tenant_id=tenant_id, customer=src).update(customer=dst),
        "events": EventBooking.objects.filter(tenant_id=tenant_id, customer=src).update(customer=dst),
    }
    src.merged_into = dst
    src.save(update_fields=["merged_into", "updated_at"])
    log_audit(tenant_id=tenant_id, user_id=user.pk, action="customer.merged", entity_type="customer",
        entity_id=str(src.pk), payload={"target_id": str(dst.pk), "reason": reason, "linked_records": counts})
    return dst, counts
