"""Industry-aware delivery fulfillment rules, independent of POS settlement.

This module is the first reusable delivery foundation. It DOES NOT create a
delivery, charge a customer, reserve stock, or post a payment. Persistent
delivery records and role-checked staff actions are separate rollout gates.
"""
from decimal import Decimal, InvalidOperation

from apps.tenants.models import OutletType


class DeliveryPolicyError(ValueError):
    """A requested delivery transition or destination is not permitted."""


DELIVERY_OUTLET_TYPES = frozenset({
    OutletType.RESTAURANT, OutletType.CAFETERIA,
    OutletType.BAR, OutletType.LOUNGE,
    OutletType.SUPERMARKET, OutletType.RETAIL,
    OutletType.LODGING_FRONT_DESK,
})

STAGES = (
    "requested", "accepted", "preparing", "ready",
    "dispatched", "delivered", "failed", "returned", "cancelled",
)

# A failed attempt may be re-dispatched after the business resolves the cause.
ALLOWED_NEXT = {
    "requested": frozenset({"accepted", "cancelled"}),
    "accepted": frozenset({"preparing", "cancelled"}),
    "preparing": frozenset({"ready", "cancelled"}),
    "ready": frozenset({"dispatched", "cancelled"}),
    "dispatched": frozenset({"delivered", "failed"}),
    "failed": frozenset({"ready", "returned", "cancelled"}),
    "delivered": frozenset(),
    "returned": frozenset(),
    "cancelled": frozenset(),
}


def validate_delivery_transition(current: str, target: str) -> None:
    """Guard legal dispatch state transitions before any persistent state write."""
    if current not in ALLOWED_NEXT or target not in ALLOWED_NEXT[current]:
        raise DeliveryPolicyError(f"Delivery cannot move from {current!r} to {target!r}.")


def validate_delivery_destination(
    *, outlet_type: str, destination_type: str,
    recipient_name: str = "", contact_phone: str = "",
    address: str = "", room_reference: str = "",
) -> None:
    """Validate destination completeness without exposing hospitality data.

    Hotel room service is an internal delivery type, not a street delivery.
    Outside deliveries always require recipient contact and physical address.
    """
    if outlet_type not in DELIVERY_OUTLET_TYPES:
        raise DeliveryPolicyError("Deliveries are not supported by this section.")
    if destination_type == "room":
        if outlet_type != OutletType.LODGING_FRONT_DESK:
            raise DeliveryPolicyError("Room deliveries require a lodging outlet.")
        if not room_reference.strip():
            raise DeliveryPolicyError("Choose a real guest room or folio before room delivery.")
        return
    if destination_type != "address":
        raise DeliveryPolicyError("Choose a delivery address or an eligible guest room.")
    if not recipient_name.strip() or not contact_phone.strip() or not address.strip():
        raise DeliveryPolicyError("Outside delivery needs a recipient name, contact and address.")
    if len(recipient_name) > 120 or len(contact_phone) > 40 or len(address) > 500:
        raise DeliveryPolicyError("Recipient or address is too long.")


def validate_delivery_charge(amount, *, currency: str) -> Decimal:
    """Validate fee input; no ledger posting or tax decision is made here."""
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise DeliveryPolicyError("Delivery fee requires a valid sale currency.")
    try:
        fee = Decimal(str(amount))
    except (ValueError, TypeError, ArithmeticError, InvalidOperation) as exc:
        raise DeliveryPolicyError("Enter a valid delivery fee.") from exc
    if not fee.is_finite() or fee < 0 or fee > Decimal("9999999999.99"):
        raise DeliveryPolicyError("Delivery fee must be nonnegative and within limits.")
    if fee != fee.quantize(Decimal("0.01")):
        raise DeliveryPolicyError("Delivery fee can have at most two decimal places.")
    return fee
