"""Workstation equipment observations never imply physical device success."""
import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.audit.models import AuditEvent
from apps.pos.models import Workstation, WorkstationHardwareCheck
from apps.pos.services.hardware import (
    browser_device_capabilities, record_hardware_check,
)
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_admin_can_record_real_observation_without_triggering_a_payment():
    a = _seed_tenant_bundle(
        name="Hardware Check", slug="hardware-check-tests",
        user_email="hardware-check@example.test",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"], outlet=a["outlet"],
        name="Till A", code="till-a",
        receipt_printer="Front printer",
    )
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    observed = record_hardware_check(
        tenant=a["tenant"], workstation_id=station.pk,
        membership=member, user=a["user"],
        test_type="receipt_printer", result="pass",
        note="Printed the non-financial sample and checked alignment",
    )
    assert observed.configured_device == "Front printer"
    assert WorkstationHardwareCheck.objects.filter(workstation=station).count() == 1
    assert AuditEvent.objects.filter(
        tenant=a["tenant"], action="workstation.hardware_check_recorded",
    ).count() == 1
    methods = browser_device_capabilities(station)
    assert methods["receipt_print"]["method"] == "browser_print_dialog"
    assert methods["drawer_open"]["available"] is False


@pytest.mark.django_db
def test_hardware_failed_observation_requires_note():
    a = _seed_tenant_bundle(
        name="Bad Hardware", slug="bad-hardware-tests",
        user_email="bad-hardware@example.test",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"], outlet=a["outlet"],
        name="Register", code="register-1",
    )
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    with pytest.raises(ValidationError):
        record_hardware_check(
            tenant=a["tenant"], workstation_id=station.pk,
            membership=member, user=a["user"],
            test_type="cash_drawer", result="fail", note="",
        )
    assert not WorkstationHardwareCheck.objects.exists()


@pytest.mark.django_db
def test_cashier_cannot_forge_admin_device_results():
    a = _seed_tenant_bundle(
        name="Worker Hardware", slug="worker-hardware-tests",
        user_email="worker-hardware@example.test",
    )
    station = Workstation.objects.create(
        tenant=a["tenant"], outlet=a["outlet"],
        name="Checkout", code="checkout-2",
    )
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    member.role = MembershipRole.SERVER
    member.sites.add(a["site"])
    member.save(update_fields=["role"])
    with pytest.raises(ValidationError):
        record_hardware_check(
            tenant=a["tenant"], workstation_id=station.pk,
            membership=member, user=a["user"],
            test_type="receipt_printer", result="pass",
        )
    assert not WorkstationHardwareCheck.objects.exists()


@pytest.mark.django_db
def test_kitchen_hardware_is_not_advertised_to_retail_only_tenant():
    a = _seed_tenant_bundle(
        name="Retail Hardware", slug="retail-hardware-tests",
        user_email="retail-hardware@example.test",
    )
    from apps.tenants.models import TenantSettings, OutletType
    a["outlet"].outlet_type = OutletType.RETAIL
    a["outlet"].save(update_fields=["outlet_type"])
    settings = TenantSettings.objects.get(tenant=a["tenant"])
    settings.business_lines = ["retail"]
    settings.save(update_fields=["business_lines"])
    station = Workstation.objects.create(
        tenant=a["tenant"], outlet=a["outlet"],
        name="Retail Till", code="retail-till",
    )
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    with pytest.raises(ValidationError):
        record_hardware_check(
            tenant=a["tenant"], workstation_id=station.pk,
            membership=member, user=a["user"],
            test_type="kitchen_display", result="pass",
        )
