from django.test import Client
from django.urls import reverse
import pytest

from apps.accounts.models import Membership
from apps.pos.models import (
    Workstation,
    WorkstationDevice,
    WorkstationDeviceAdapter,
    WorkstationDeviceCommand,
    WorkstationDeviceHealth,
    WorkstationDeviceType,
    WorkstationHardwareCheck,
    Order,
)
from apps.pos.services.device_adapters import (
    device_status_summary,
    record_adapter_heartbeat,
)
from apps.pos.services.hardware import record_hardware_check
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_KEY,
    STAFF_SESSION_SITE_KEY,
    STAFF_SESSION_TENANT_KEY,
)
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def _login(client, fixture):
    assert client.login(
        username=fixture["user"].email,
        password="TestPass9!",
    )
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(fixture["tenant"].pk)
    session[STAFF_SESSION_SITE_KEY] = str(fixture["site"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(fixture["outlet"].pk)
    session.save()


@pytest.mark.django_db
def test_device_registry_rejects_unsafe_adapter_combination():
    a = _seed_tenant_bundle(
        name="Device Registry",
        slug="device-registry",
        user_email="device-registry@test.local",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        name="Front Till",
        code="front-till",
    )
    client = Client()
    _login(client, a)
    response = client.post(
        reverse(
            "staff-workstation-device-create",
            kwargs={"workstation_id": station.pk},
        ),
        {
            "device_type": WorkstationDeviceType.CASH_DRAWER,
            "adapter": WorkstationDeviceAdapter.KEYBOARD_WEDGE,
            "label": "Drawer 1",
            "is_active": "on",
        },
    )
    assert response.status_code == 400
    assert b"cannot safely control" in response.content
    assert not WorkstationDevice.objects.exists()


@pytest.mark.django_db
def test_browser_print_status_never_claims_physical_online():
    a = _seed_tenant_bundle(
        name="Browser Hardware",
        slug="browser-hardware",
        user_email="browser-hardware@test.local",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        name="Till",
        code="browser-till",
    )
    device = WorkstationDevice.objects.create(
        tenant=a["tenant"],
        workstation=station,
        device_type=WorkstationDeviceType.RECEIPT_PRINTER,
        adapter=WorkstationDeviceAdapter.BROWSER_PRINT,
        label="Front receipt printer",
        created_by=a["user"],
    )
    summary = device_status_summary(device)
    assert summary["health"] == WorkstationDeviceHealth.UNKNOWN
    assert summary["status_label"] == "Browser capability"
    assert summary["automatic_control"] is False
    assert summary["live_health"] is False

    member = Membership.objects.get(
        tenant=a["tenant"],
        user=a["user"],
    )
    record_hardware_check(
        tenant=a["tenant"],
        workstation_id=station.pk,
        membership=member,
        user=a["user"],
        test_type="receipt_printer",
        result="pass",
        note="Physical sample printed correctly",
    )
    summary = device_status_summary(device)
    assert summary["health"] == WorkstationDeviceHealth.UNKNOWN
    assert summary["status_label"] == "Observed working"


@pytest.mark.django_db
def test_local_bridge_health_uses_bounded_retry_and_recovers():
    a = _seed_tenant_bundle(
        name="Bridge Hardware",
        slug="bridge-hardware",
        user_email="bridge-hardware@test.local",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        name="Till",
        code="bridge-till",
    )
    device = WorkstationDevice.objects.create(
        tenant=a["tenant"],
        workstation=station,
        device_type=WorkstationDeviceType.CASH_DRAWER,
        adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
        label="Till drawer",
        created_by=a["user"],
    )

    record_adapter_heartbeat(
        device=device,
        user=a["user"],
        success=False,
        latency_ms=120,
        error="Bridge command timed out",
    )
    device.refresh_from_db()
    assert device.health_status == WorkstationDeviceHealth.DEGRADED
    assert device.consecutive_failures == 1

    record_adapter_heartbeat(
        device=device,
        user=a["user"],
        success=False,
        latency_ms=150,
        error="Bridge command timed out",
    )
    record_adapter_heartbeat(
        device=device,
        user=a["user"],
        success=False,
        latency_ms=180,
        error="Bridge command timed out",
    )
    device.refresh_from_db()
    assert device.health_status == WorkstationDeviceHealth.OFFLINE
    assert device.consecutive_failures == 3

    record_adapter_heartbeat(
        device=device,
        user=a["user"],
        success=True,
        latency_ms=24,
    )
    device.refresh_from_db()
    assert device.health_status == WorkstationDeviceHealth.ONLINE
    assert device.consecutive_failures == 0
    assert device.last_error == ""
    assert device.last_success_at is not None


@pytest.mark.django_db
def test_device_edit_fails_closed_across_tenants():
    a = _seed_tenant_bundle(
        name="Device Tenant A",
        slug="device-tenant-a",
        user_email="device-a@test.local",
    )
    b = _seed_tenant_bundle(
        name="Device Tenant B",
        slug="device-tenant-b",
        user_email="device-b@test.local",
    )
    station_b = Workstation.objects.create(
        tenant=b["tenant"],
        outlet=b["outlet"],
        name="Private till",
        code="private-till",
    )
    device_b = WorkstationDevice.objects.create(
        tenant=b["tenant"],
        workstation=station_b,
        device_type=WorkstationDeviceType.BARCODE_SCANNER,
        adapter=WorkstationDeviceAdapter.KEYBOARD_WEDGE,
        label="Private scanner",
        created_by=b["user"],
    )

    client = Client()
    _login(client, a)
    response = client.get(
        reverse(
            "staff-workstation-device-edit",
            kwargs={
                "workstation_id": station_b.pk,
                "device_id": device_b.pk,
            },
        )
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_device_registry_appears_in_equipment_status_ui():
    a = _seed_tenant_bundle(
        name="Device UI",
        slug="device-ui",
        user_email="device-ui@test.local",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        name="Checkout",
        code="device-ui-till",
    )
    WorkstationDevice.objects.create(
        tenant=a["tenant"],
        workstation=station,
        device_type=WorkstationDeviceType.BARCODE_SCANNER,
        adapter=WorkstationDeviceAdapter.KEYBOARD_WEDGE,
        label="Counter scanner",
        created_by=a["user"],
    )
    client = Client()
    _login(client, a)
    page = client.get(
        reverse("staff-workstation-test", kwargs={"workstation_id": station.pk})
    )
    assert page.status_code == 200
    assert b"Registered devices" in page.content
    assert b"Counter scanner" in page.content
    assert b"Keyboard-wedge input" in page.content
    assert b"Browser capability" in page.content


@pytest.mark.django_db
def test_equipment_diagnostics_can_queue_safe_commands_but_not_open_drawer():
    a = _seed_tenant_bundle(
        name="Safe Device Commands",
        slug="safe-device-commands",
        user_email="safe-device@test.local",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        name="Checkout",
        code="safe-command-till",
    )
    printer = WorkstationDevice.objects.create(
        tenant=a["tenant"],
        workstation=station,
        device_type=WorkstationDeviceType.RECEIPT_PRINTER,
        adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
        label="Receipt printer",
        created_by=a["user"],
    )
    drawer = WorkstationDevice.objects.create(
        tenant=a["tenant"],
        workstation=station,
        device_type=WorkstationDeviceType.CASH_DRAWER,
        adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
        label="Cash drawer",
        created_by=a["user"],
    )
    scale = WorkstationDevice.objects.create(
        tenant=a["tenant"],
        workstation=station,
        device_type=WorkstationDeviceType.WEIGHING_SCALE,
        adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
        label="Counter scale",
        created_by=a["user"],
    )
    client = Client()
    _login(client, a)

    queued = client.post(
        reverse("staff-workstation-test", kwargs={"workstation_id": station.pk}),
        {
            "action": "queue_device_command",
            "device_id": str(printer.pk),
            "command_type": "print_receipt",
        },
    )
    assert queued.status_code == 302
    command = WorkstationDeviceCommand.objects.get(device=printer)
    assert command.command_type == "print_receipt"
    assert command.payload["diagnostic"] is True
    assert command.payload["document_type"] == "device_test"

    denied = client.post(
        reverse("staff-workstation-test", kwargs={"workstation_id": station.pk}),
        {
            "action": "queue_device_command",
            "device_id": str(drawer.pk),
            "command_type": "open_drawer",
        },
    )
    assert denied.status_code == 400
    assert not WorkstationDeviceCommand.objects.filter(
        device=drawer,
        command_type="open_drawer",
    ).exists()

    tare = client.post(
        reverse("staff-workstation-test", kwargs={"workstation_id": station.pk}),
        {
            "action": "queue_device_command",
            "device_id": str(scale.pk),
            "command_type": "tare_scale",
        },
    )
    assert tare.status_code == 302
    assert WorkstationDeviceCommand.objects.filter(
        device=scale,
        command_type="tare_scale",
        payload__diagnostic=True,
    ).exists()


@pytest.mark.django_db
def test_scanner_burst_diagnostic_records_metrics_without_barcode_or_basket_side_effects():
    a = _seed_tenant_bundle(
        name="Scanner Diagnostics",
        slug="scanner-diagnostics",
        user_email="scanner-diagnostics@test.local",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        name="Rapid Scan Till",
        code="rapid-scan-till",
    )
    client = Client()
    _login(client, a)
    before_orders = Order.objects.filter(tenant=a["tenant"]).count()
    before_commands = WorkstationDeviceCommand.objects.filter(
        tenant=a["tenant"],
        workstation=station,
    ).count()

    response = client.post(
        reverse("staff-workstation-test", kwargs={"workstation_id": station.pk}),
        {
            "action": "record_scanner_diagnostic",
            "character_count": "13",
            "duration_ms": "84",
            "average_gap_ms": "6",
            "max_gap_ms": "11",
            "enter_terminated": "1",
            "barcode_value": "SHOULD-NOT-BE-STORED",
        },
    )
    assert response.status_code == 302
    check = WorkstationHardwareCheck.objects.get(
        tenant=a["tenant"],
        workstation=station,
        test_type="barcode_scanner",
    )
    assert check.result == "pass"
    assert check.evidence == {
        "character_count": 13,
        "duration_ms": 84,
        "average_gap_ms": 6,
        "max_gap_ms": 11,
        "enter_terminated": True,
    }
    assert "SHOULD-NOT-BE-STORED" not in check.note
    assert "SHOULD-NOT-BE-STORED" not in str(check.evidence)
    assert Order.objects.filter(tenant=a["tenant"]).count() == before_orders
    assert WorkstationDeviceCommand.objects.filter(
        tenant=a["tenant"],
        workstation=station,
    ).count() == before_commands

    invalid = client.post(
        reverse("staff-workstation-test", kwargs={"workstation_id": station.pk}),
        {
            "action": "record_scanner_diagnostic",
            "character_count": "500",
            "duration_ms": "-1",
            "average_gap_ms": "0",
            "max_gap_ms": "0",
            "enter_terminated": "1",
        },
    )
    assert invalid.status_code == 400
    assert WorkstationHardwareCheck.objects.filter(
        tenant=a["tenant"],
        workstation=station,
        test_type="barcode_scanner",
    ).count() == 1
