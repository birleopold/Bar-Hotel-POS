from datetime import timedelta

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
import pytest

from apps.pos.models import (
    Workstation,
    WorkstationDevice,
    WorkstationDeviceAdapter,
    WorkstationDeviceCommand,
    WorkstationDeviceCommandStatus,
    WorkstationDeviceCommandType,
    WorkstationDeviceHealth,
    WorkstationDeviceType,
)
from apps.pos.services.hardware_bridge import (
    enqueue_device_command,
    provision_bridge_credential,
    revoke_bridge_credential,
)
from apps.tenants.models import TenantDomain
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@override_settings(
    ALLOWED_HOSTS=[
        "bridge-hardware.pos.example.test",
        "bridge-other.pos.example.test",
    ],
    TENANT_PLATFORM_DOMAIN="pos.example.test",
    TENANT_CENTRAL_HOSTS=["pos.example.test"],
)
@pytest.mark.django_db
def test_local_bridge_http_command_retry_success_and_revocation():
    a = _seed_tenant_bundle(
        name="Bridge Hardware",
        slug="bridge-hardware",
        user_email="bridge-owner@test.local",
    )
    TenantDomain.objects.create(
        tenant=a["tenant"],
        hostname="bridge-hardware.pos.example.test",
        kind=TenantDomain.Kind.PLATFORM,
        status=TenantDomain.Status.ACTIVE,
    )
    station = Workstation.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        name="Front Till",
        code="bridge-front-till",
    )
    device = WorkstationDevice.objects.create(
        tenant=a["tenant"],
        workstation=station,
        device_type=WorkstationDeviceType.RECEIPT_PRINTER,
        adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
        label="Front thermal printer",
        created_by=a["user"],
    )
    credential, token = provision_bridge_credential(
        tenant=a["tenant"],
        workstation=station,
        user=a["user"],
        label="Front PC bridge",
        expires_days=30,
    )
    assert token.startswith(f"{credential.pk}.")
    secret = token.split(".", 1)[1]
    assert secret
    assert secret not in credential.token_hash

    command, replay = enqueue_device_command(
        tenant=a["tenant"],
        device=device,
        user=a["user"],
        command_type=WorkstationDeviceCommandType.PRINT_RECEIPT,
        idempotency_key="receipt-test-001",
        payload={
            "document_type": "device_test",
            "text": "DEVICE TEST ONLY",
        },
    )
    assert replay is False
    same, replay = enqueue_device_command(
        tenant=a["tenant"],
        device=device,
        user=a["user"],
        command_type=WorkstationDeviceCommandType.PRINT_RECEIPT,
        idempotency_key="receipt-test-001",
        payload={"ignored_on_replay": True},
    )
    assert replay is True
    assert same.pk == command.pk

    client = Client()
    poll = client.post(
        reverse("hardware-bridge-poll"),
        data={"limit": 10},
        content_type="application/json",
        HTTP_HOST="bridge-hardware.pos.example.test",
        HTTP_X_HARDWARE_BRIDGE_TOKEN=token,
    )
    assert poll.status_code == 200
    body = poll.json()
    assert body["workstation_id"] == str(station.pk)
    assert len(body["commands"]) == 1
    assert body["commands"][0]["id"] == str(command.pk)
    assert body["commands"][0]["command_type"] == "print_receipt"

    failed = client.post(
        reverse("hardware-bridge-report"),
        data={
            "command_id": str(command.pk),
            "success": False,
            "latency_ms": 250,
            "error": "Printer unavailable",
        },
        content_type="application/json",
        HTTP_HOST="bridge-hardware.pos.example.test",
        HTTP_X_HARDWARE_BRIDGE_TOKEN=token,
    )
    assert failed.status_code == 200
    command.refresh_from_db()
    device.refresh_from_db()
    assert command.status == WorkstationDeviceCommandStatus.PENDING
    assert command.attempts == 1
    assert command.not_before is not None
    assert device.health_status == WorkstationDeviceHealth.DEGRADED

    WorkstationDeviceCommand.objects.filter(pk=command.pk).update(
        not_before=timezone.now() - timedelta(seconds=1)
    )
    claimed_again = client.post(
        reverse("hardware-bridge-poll"),
        data={"limit": 10},
        content_type="application/json",
        HTTP_HOST="bridge-hardware.pos.example.test",
        HTTP_X_HARDWARE_BRIDGE_TOKEN=token,
    )
    assert claimed_again.status_code == 200
    assert len(claimed_again.json()["commands"]) == 1

    success = client.post(
        reverse("hardware-bridge-report"),
        data={
            "command_id": str(command.pk),
            "success": True,
            "latency_ms": 31,
            "result": {"printed": True},
        },
        content_type="application/json",
        HTTP_HOST="bridge-hardware.pos.example.test",
        HTTP_X_HARDWARE_BRIDGE_TOKEN=token,
    )
    assert success.status_code == 200
    command.refresh_from_db()
    device.refresh_from_db()
    credential.refresh_from_db()
    assert command.status == WorkstationDeviceCommandStatus.SUCCEEDED
    assert command.result == {"printed": True}
    assert command.attempts == 2
    assert device.health_status == WorkstationDeviceHealth.ONLINE
    assert device.last_latency_ms == 31
    assert credential.last_seen_at is not None

    revoke_bridge_credential(
        credential=credential,
        user=a["user"],
        reason="Replacing local computer",
    )
    denied = client.post(
        reverse("hardware-bridge-poll"),
        data={"limit": 10},
        content_type="application/json",
        HTTP_HOST="bridge-hardware.pos.example.test",
        HTTP_X_HARDWARE_BRIDGE_TOKEN=token,
    )
    assert denied.status_code in {401, 403}


@override_settings(
    ALLOWED_HOSTS=[
        "bridge-hardware.pos.example.test",
        "bridge-other.pos.example.test",
    ],
    TENANT_PLATFORM_DOMAIN="pos.example.test",
    TENANT_CENTRAL_HOSTS=["pos.example.test"],
)
@pytest.mark.django_db
def test_bridge_token_cannot_cross_tenant_hostname():
    a = _seed_tenant_bundle(
        name="Bridge Hardware",
        slug="bridge-hardware-cross",
        user_email="bridge-cross-a@test.local",
    )
    b = _seed_tenant_bundle(
        name="Bridge Other",
        slug="bridge-other-cross",
        user_email="bridge-cross-b@test.local",
    )
    TenantDomain.objects.create(
        tenant=a["tenant"],
        hostname="bridge-hardware.pos.example.test",
        kind=TenantDomain.Kind.PLATFORM,
        status=TenantDomain.Status.ACTIVE,
    )
    TenantDomain.objects.create(
        tenant=b["tenant"],
        hostname="bridge-other.pos.example.test",
        kind=TenantDomain.Kind.PLATFORM,
        status=TenantDomain.Status.ACTIVE,
    )
    station = Workstation.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        name="A Till",
        code="bridge-a",
    )
    credential, token = provision_bridge_credential(
        tenant=a["tenant"],
        workstation=station,
        user=a["user"],
        label="A bridge",
        expires_days=30,
    )
    client = Client()
    denied = client.post(
        reverse("hardware-bridge-poll"),
        data={"limit": 10},
        content_type="application/json",
        HTTP_HOST="bridge-other.pos.example.test",
        HTTP_X_HARDWARE_BRIDGE_TOKEN=token,
    )
    assert denied.status_code in {401, 403}
