"""Tenant-safe first-party delivery registration (no dispatch or ledger changes).

Delivery is separate from payment, stock and pickup. Only a manager at an
explicitly opted-in outlet may register a paid first-party delivery.
"""
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.pos.models import (
    Order, OrderStatus, OrderDelivery, OutletDeliverySettings,
    Payment, RetailPickup,
)
from .delivery_policy import (
    DeliveryPolicyError, validate_delivery_charge, validate_delivery_destination,
)


MANAGER_ROLES = frozenset({
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
})


def _authorized_delivery_manager(*, membership, user, tenant_id, outlet_id):
    return bool(
        membership is not None and membership.is_active
        and membership.user_id == user.pk
        and membership.tenant_id == tenant_id
        and membership.role in MANAGER_ROLES
        and outlet_belongs_to_membership(membership, outlet_id)
    )


@transaction.atomic
def set_outlet_delivery_enabled(*, outlet, enabled: bool, user, membership):
    """Opt an individual outlet in or out; other tenant outlets remain off."""
    if not _authorized_delivery_manager(
        membership=membership, user=user,
        tenant_id=outlet.site.tenant_id, outlet_id=outlet.pk,
    ):
        raise ValidationError({"delivery": "Not authorized to configure this outlet."})
    if not isinstance(enabled, bool):
        raise ValidationError({"enabled": "Choose true or false."})
    setting, _ = OutletDeliverySettings.objects.select_for_update().get_or_create(
        outlet=outlet, defaults={"tenant_id":outlet.site.tenant_id, "is_enabled":False},
    )
    if setting.tenant_id != outlet.site.tenant_id:
        raise ValidationError({"delivery": "Outlet delivery configuration has an invalid tenant."})
    if setting.is_enabled != enabled:
        setting.is_enabled = enabled
        setting.save(update_fields=["is_enabled", "updated_at"])
        log_audit(
            tenant_id=setting.tenant_id, user_id=user.pk,
            action="delivery.outlet_enabled_changed",
            entity_type="outlet_delivery_settings", entity_id=str(setting.pk),
            payload={"outlet_id":str(outlet.pk), "enabled":enabled},
        )
    return setting


@transaction.atomic
def register_paid_order_delivery(
    *, order, user, membership, destination_type,
    recipient_name="", contact_phone="", address="", room_reference="",
    instructions="", promised_at=None,
):
    """Register initial paid-only fulfillment, preserving the existing sale.

    This does not dispatch, charge a fee, deduct stock, or reserve units.
    Returns (existing_or_new_delivery, replayed). Replayed registration is safe.
    """
    locked = Order.objects.select_for_update().select_related("outlet__site").get(
        pk=order.pk,
    )
    if not _authorized_delivery_manager(
        membership=membership, user=user, tenant_id=locked.tenant_id,
        outlet_id=locked.outlet_id,
    ):
        raise ValidationError({"delivery": "Not authorized for this outlet."})
    if locked.outlet.site.tenant_id != locked.tenant_id:
        raise ValidationError({"delivery": "Order outlet and tenant do not match."})
    setting = OutletDeliverySettings.objects.filter(
        tenant_id=locked.tenant_id, outlet_id=locked.outlet_id,
        is_enabled=True,
    ).first()
    if setting is None:
        raise ValidationError({"delivery": "Delivery is not enabled for this outlet."})
    try:
        validate_delivery_destination(
            outlet_type=locked.outlet.outlet_type,
            destination_type=destination_type,
            recipient_name=recipient_name, contact_phone=contact_phone,
            address=address, room_reference=room_reference,
        )
    except DeliveryPolicyError as exc:
        raise ValidationError({"delivery":str(exc)}) from exc
    if not isinstance(instructions, str) or len(instructions) > 500:
        raise ValidationError({"instructions":"Use at most 500 characters."})
    if promised_at is not None:
        from django.utils import timezone
        if timezone.is_naive(promised_at):
            raise ValidationError({"promised_at":"Use a time with timezone information."})
        if promised_at < timezone.now():
            raise ValidationError({"promised_at":"Delivery time cannot be in the past."})
    if locked.status != OrderStatus.CLOSED or not locked.is_paid:
        raise ValidationError({"order":"Fully settle the sale before registering delivery."})
    # Order.is_paid alone is not enough: payment ledger is authoritative.
    paid = Payment.objects.filter(
        tenant_id=locked.tenant_id, order=locked,
    ).aggregate(v=Sum("amount"))["v"] or 0
    if paid < locked.total:
        raise ValidationError({"order":"Recorded payment does not cover the sale."})
    if locked.refunds.exists():
        raise ValidationError({"order":"Refunded sale requires supervisor review."})
    if RetailPickup.objects.filter(
        tenant_id=locked.tenant_id, order=locked,
    ).exists():
        raise ValidationError({"order":"This sale is already assigned for customer pickup."})
    existing = OrderDelivery.objects.filter(
        tenant_id=locked.tenant_id, order=locked,
    ).first()
    if existing:
        if (
            existing.destination_type == destination_type
            and existing.recipient_name == recipient_name
            and existing.contact_phone == contact_phone
            and existing.address == address
            and existing.room_reference == room_reference
            and existing.instructions == instructions
            and existing.promised_at == promised_at
        ):
            return existing, True
        raise ValidationError({"order":"Delivery already registered; do not overwrite its destination."})
    # Fees must be part of the original POS order total, before payment.
    # D01 must never invent a second charge for an already settled sale.
    validate_delivery_charge("0", currency=locked.currency)
    delivery = OrderDelivery.objects.create(
        tenant_id=locked.tenant_id, outlet_id=locked.outlet_id,
        order=locked, destination_type=destination_type,
        recipient_name=recipient_name, contact_phone=contact_phone,
        address=address, room_reference=room_reference,
        instructions=instructions, promised_at=promised_at,
        fee=0, currency=locked.currency, created_by=user,
    )
    log_audit(
        tenant_id=locked.tenant_id, user_id=user.pk,
        action="delivery.registered", entity_type="order_delivery",
        entity_id=str(delivery.pk),
        payload={
            "order_id":str(locked.pk), "outlet_id":str(locked.outlet_id),
            "destination_type":destination_type,
            # Do not expose customer address/name/phone to generic audit logs.
        },
    )
    return delivery, False
