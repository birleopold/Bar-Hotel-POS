"""Cross-business delivery policy contract; no delivery tables or payments yet."""
from decimal import Decimal
from django.test import SimpleTestCase

from apps.pos.services.delivery_policy import (
    ALLOWED_NEXT, DeliveryPolicyError, validate_delivery_charge,
    validate_delivery_dispatch,
    validate_delivery_destination, validate_delivery_transition,
)
from apps.tenants.models import OutletType


class DeliveryPolicyTests(SimpleTestCase):
    def test_external_delivery_requires_complete_destination_for_every_supported_line(self):
        for line in (
            OutletType.RESTAURANT, OutletType.CAFETERIA,
            OutletType.BAR, OutletType.LOUNGE,
            OutletType.SUPERMARKET, OutletType.RETAIL,
            OutletType.LODGING_FRONT_DESK,
        ):
            with self.subTest(line=line):
                validate_delivery_destination(
                    outlet_type=line, destination_type="address",
                    recipient_name="Customer", contact_phone="+256700000000",
                    address="Kampala, Uganda",
                )
                with self.assertRaises(DeliveryPolicyError):
                    validate_delivery_destination(
                        outlet_type=line, destination_type="address",
                        recipient_name="Customer", contact_phone="", address="Kampala",
                    )

    def test_room_service_is_internal_lodging_delivery_only(self):
        validate_delivery_destination(
            outlet_type=OutletType.LODGING_FRONT_DESK,
            destination_type="room", room_reference="Room 204",
        )
        for line in (OutletType.RETAIL, OutletType.RESTAURANT, OutletType.BAR):
            with self.subTest(line=line), self.assertRaises(DeliveryPolicyError):
                validate_delivery_destination(
                    outlet_type=line, destination_type="room", room_reference="204",
                )
        with self.assertRaises(DeliveryPolicyError):
            validate_delivery_destination(
                outlet_type=OutletType.LODGING_FRONT_DESK,
                destination_type="room", room_reference="",
            )

    def test_null_or_nontext_destination_is_validation_error_not_server_error(self):
        for broken in (None, 42, {}, []):
            with self.subTest(value=broken):
                with self.assertRaises(DeliveryPolicyError):
                    validate_delivery_destination(
                        outlet_type=OutletType.RETAIL, destination_type="address",
                        recipient_name="Recipient", contact_phone="0700000000",
                        address=broken,
                    )
                with self.assertRaises(DeliveryPolicyError):
                    validate_delivery_destination(
                        outlet_type=OutletType.LODGING_FRONT_DESK,
                        destination_type="room", room_reference=broken,
                    )

    def test_dispatch_transitions_reject_skipping_and_terminal_reopening(self):
        for first, second in zip(
            ("requested", "accepted", "preparing", "ready", "dispatched"),
            ("accepted", "preparing", "ready", "dispatched", "delivered"),
        ):
            validate_delivery_transition(first, second)
        validate_delivery_transition("failed", "ready")
        for first, second in (
            ("requested", "delivered"), ("accepted", "dispatched"),
            ("delivered", "dispatched"), ("cancelled", "ready"),
            ("returned", "delivered"), ("unknown", "delivered"),
        ):
            with self.subTest(first=first, second=second):
                with self.assertRaises(DeliveryPolicyError):
                    validate_delivery_transition(first, second)
        self.assertEqual(ALLOWED_NEXT["delivered"], frozenset())

    def test_fee_validation_does_not_collect_money(self):
        self.assertEqual(validate_delivery_charge("2500", currency="UGX"), Decimal("2500"))
        self.assertEqual(validate_delivery_charge("0", currency="UGX"), Decimal("0"))
        for amount in ("-1", "NaN", "Infinity", "1.234", "not a fee", None):
            with self.subTest(amount=amount), self.assertRaises(DeliveryPolicyError):
                validate_delivery_charge(amount, currency="UGX")
        with self.assertRaises(DeliveryPolicyError):
            validate_delivery_charge("1000", currency="")

    def test_first_release_dispatch_requires_settlement_and_worker(self):
        validate_delivery_dispatch(
            order_status="closed", is_paid=True,
            assigned_driver_id="approved-driver-id",
        )
        for state, paid, driver, refunds in (
            ("open", False, "driver", False),
            ("closed", False, "driver", False),
            ("open", True, "driver", False),
            ("closed", True, None, False),
            ("closed", True, "driver", True),
        ):
            with self.subTest(state=state, paid=paid, driver=driver, refunds=refunds):
                with self.assertRaises(DeliveryPolicyError):
                    validate_delivery_dispatch(
                        order_status=state, is_paid=paid,
                        assigned_driver_id=driver, has_refunds=refunds,
                    )
