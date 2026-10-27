from decimal import Decimal

from django.test import TestCase

from apps.pos.models import (
    Order,
    OrderStatus,
    PosShift,
    Workstation,
    WorkstationDevice,
    WorkstationDeviceAdapter,
    WorkstationDeviceCommand,
    WorkstationDeviceType,
)
from apps.pos.services.payments import record_order_payment
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


class CashDrawerSettlementBridgeTests(TestCase):
    def setUp(self):
        self.bundle = _seed_tenant_bundle(
            name="Drawer Settlement",
            slug="drawer-settlement",
            user_email="drawer-settlement@test.local",
        )
        self.station = Workstation.objects.create(
            tenant=self.bundle["tenant"],
            outlet=self.bundle["outlet"],
            name="Checkout",
            code="drawer-settlement-till",
        )
        self.shift = PosShift.objects.create(
            tenant=self.bundle["tenant"],
            outlet=self.bundle["outlet"],
            workstation=self.station,
            opened_by=self.bundle["user"],
            opening_cash=Decimal("0.00"),
        )
        self.drawer = WorkstationDevice.objects.create(
            tenant=self.bundle["tenant"],
            workstation=self.station,
            device_type=WorkstationDeviceType.CASH_DRAWER,
            adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
            label="Main cash drawer",
            created_by=self.bundle["user"],
        )

    def _order(self):
        return Order.objects.create(
            tenant=self.bundle["tenant"],
            outlet=self.bundle["outlet"],
            status=OrderStatus.OPEN,
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
            created_by=self.bundle["user"],
        )

    def test_committed_cash_payment_queues_one_idempotent_drawer_command(self):
        order = self._order()
        with self.captureOnCommitCallbacks(execute=True):
            payment, replay = record_order_payment(
                order=order,
                user=self.bundle["user"],
                amount=Decimal("10.00"),
                method="cash",
                idempotency_key="drawer-cash-payment",
                workstation_id=self.station.pk,
                shift_id=self.shift.pk,
            )
        self.assertFalse(replay)
        command = WorkstationDeviceCommand.objects.get(
            device=self.drawer,
            command_type="open_drawer",
        )
        self.assertEqual(
            command.idempotency_key,
            f"cash-payment:{payment.pk}:drawer:{self.drawer.pk}",
        )
        self.assertEqual(command.payload["payment_id"], str(payment.pk))
        self.assertEqual(command.payload["order_id"], str(order.pk))

        # A payment idempotency replay cannot create a second drawer command.
        with self.captureOnCommitCallbacks(execute=True):
            replayed, replay = record_order_payment(
                order=order,
                user=self.bundle["user"],
                amount=Decimal("10.00"),
                method="cash",
                idempotency_key="drawer-cash-payment",
                workstation_id=self.station.pk,
                shift_id=self.shift.pk,
            )
        self.assertTrue(replay)
        self.assertEqual(replayed.pk, payment.pk)
        self.assertEqual(
            WorkstationDeviceCommand.objects.filter(
                device=self.drawer,
                command_type="open_drawer",
            ).count(),
            1,
        )

    def test_non_cash_payment_does_not_queue_drawer_open(self):
        order = self._order()
        with self.captureOnCommitCallbacks(execute=True):
            record_order_payment(
                order=order,
                user=self.bundle["user"],
                amount=Decimal("10.00"),
                method="card",
                idempotency_key="drawer-card-payment",
                workstation_id=self.station.pk,
                shift_id=self.shift.pk,
            )
        self.assertFalse(
            WorkstationDeviceCommand.objects.filter(
                device=self.drawer,
                command_type="open_drawer",
            ).exists()
        )
