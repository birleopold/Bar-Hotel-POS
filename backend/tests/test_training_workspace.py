from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.catalog.models import MenuItem
from apps.customers.models import Customer
from apps.integrations.models import EfrisSubmission
from apps.integrations.services import enqueue_efris_submission_for_cashbook_entry
from apps.inventory.models import StockBalance
from apps.pos.models import (
    Order,
    Payment,
    Refund,
    SupermarketLineReturn,
    Workstation,
    WorkstationDevice,
    WorkstationDeviceAdapter,
    WorkstationDeviceType,
)
from apps.pos.services.hardware_bridge import enqueue_device_command
from apps.purchasing.models import PurchaseOrder, Supplier
from apps.tenants.models import TrainingWorkspaceState
from apps.tenants.training import seed_retail_training_workspace
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def _make_training_bundle():
    bundle = _seed_tenant_bundle(
        name="Retail Training",
        slug="retail-training-workspace",
        user_email="training-owner@test.local",
    )
    tenant = bundle["tenant"]
    tenant.is_training = True
    tenant.save(update_fields=["is_training", "updated_at"])
    bundle["outlet"].outlet_type = "supermarket"
    bundle["outlet"].save(update_fields=["outlet_type", "updated_at"])
    settings_obj = tenant.settings
    settings_obj.business_lines = ["supermarket"]
    settings_obj.default_currency = "UGX"
    settings_obj.efris_enabled = True
    settings_obj.save(
        update_fields=[
            "business_lines",
            "default_currency",
            "efris_enabled",
            "updated_at",
        ]
    )
    return bundle


@pytest.mark.django_db
def test_training_seed_creates_real_internal_sample_pack_without_external_queue():
    bundle = _make_training_bundle()
    state, replay = seed_retail_training_workspace(
        tenant=bundle["tenant"],
        user=bundle["user"],
    )
    assert replay is False
    assert state.generation == 1
    assert len(state.sample_ids["menu_item_ids"]) == 4
    assert MenuItem.objects.filter(
        tenant=bundle["tenant"],
        pk__in=state.sample_ids["menu_item_ids"],
    ).count() == 4
    assert Customer.objects.filter(
        tenant=bundle["tenant"],
        pk__in=state.sample_ids["customer_ids"],
    ).count() == 1
    assert Supplier.objects.filter(
        tenant=bundle["tenant"],
        pk__in=state.sample_ids["supplier_ids"],
    ).count() == 1
    assert PurchaseOrder.objects.filter(
        tenant=bundle["tenant"],
        pk__in=state.sample_ids["purchase_order_ids"],
    ).count() == 1
    order = Order.objects.get(
        tenant=bundle["tenant"],
        pk__in=state.sample_ids["order_ids"],
    )
    assert order.is_paid is True
    assert Payment.objects.filter(order=order, amount=Decimal("6500.00")).exists()
    assert Refund.objects.filter(order=order, amount=Decimal("2000.00")).exists()
    assert SupermarketLineReturn.objects.filter(
        order=order,
        quantity=Decimal("1.000"),
    ).exists()
    assert StockBalance.objects.filter(
        tenant=bundle["tenant"],
        menu_item__sku="TRAIN-SOAP",
        quantity=Decimal("3.000"),
        cost_basis_complete=True,
    ).exists()
    assert not EfrisSubmission.objects.filter(tenant=bundle["tenant"]).exists()

    same, replay = seed_retail_training_workspace(
        tenant=bundle["tenant"],
        user=bundle["user"],
    )
    assert replay is True
    assert same.pk == state.pk
    assert same.generation == 1


@pytest.mark.django_db
def test_training_reset_rebuilds_managed_pack_but_preserves_setup():
    bundle = _make_training_bundle()
    station = Workstation.objects.create(
        tenant=bundle["tenant"],
        outlet=bundle["outlet"],
        name="Training till",
        code="training-till",
    )
    original_member_count = bundle["tenant"].memberships.count()
    original_outlet_id = bundle["outlet"].pk
    first, _ = seed_retail_training_workspace(
        tenant=bundle["tenant"],
        user=bundle["user"],
    )
    first_order_ids = set(first.sample_ids["order_ids"])
    first_product_ids = set(first.sample_ids["menu_item_ids"])

    reset, replay = seed_retail_training_workspace(
        tenant=bundle["tenant"],
        user=bundle["user"],
        reset=True,
    )
    assert replay is False
    assert reset.generation == 2
    assert set(reset.sample_ids["order_ids"]).isdisjoint(first_order_ids)
    assert set(reset.sample_ids["menu_item_ids"]).isdisjoint(first_product_ids)
    assert not Order.objects.filter(pk__in=first_order_ids).exists()
    assert not MenuItem.objects.filter(pk__in=first_product_ids).exists()
    assert bundle["tenant"].memberships.count() == original_member_count
    assert bundle["tenant"].sites.filter(outlets__pk=original_outlet_id).exists()
    assert Workstation.objects.filter(pk=station.pk, tenant=bundle["tenant"]).exists()
    assert reset.exercise_progress == {}


@pytest.mark.django_db
def test_live_tenant_cannot_seed_or_reset_training_pack():
    bundle = _seed_tenant_bundle(
        name="Live Retail",
        slug="live-retail-training-denial",
        user_email="live-training-denial@test.local",
    )
    bundle["tenant"].settings.business_lines = ["supermarket"]
    bundle["tenant"].settings.save(update_fields=["business_lines", "updated_at"])
    with pytest.raises(Exception) as exc:
        seed_retail_training_workspace(
            tenant=bundle["tenant"],
            user=bundle["user"],
        )
    assert "isolated training workspace" in str(exc.value)
    assert not TrainingWorkspaceState.objects.filter(
        tenant=bundle["tenant"]
    ).exists()


@pytest.mark.django_db
def test_training_hardware_and_efris_side_effects_are_blocked():
    bundle = _make_training_bundle()
    station = Workstation.objects.create(
        tenant=bundle["tenant"],
        outlet=bundle["outlet"],
        name="Training register",
        code="training-register",
    )
    device = WorkstationDevice.objects.create(
        tenant=bundle["tenant"],
        workstation=station,
        device_type=WorkstationDeviceType.RECEIPT_PRINTER,
        adapter=WorkstationDeviceAdapter.LOCAL_BRIDGE,
        label="Training printer",
        created_by=bundle["user"],
    )
    with pytest.raises(Exception) as exc:
        enqueue_device_command(
            tenant=bundle["tenant"],
            device=device,
            user=bundle["user"],
            command_type="print_receipt",
            idempotency_key="training-print-denied",
            payload={"text": "should not print"},
        )
    assert "disabled in training workspaces" in str(exc.value)

    state, _ = seed_retail_training_workspace(
        tenant=bundle["tenant"],
        user=bundle["user"],
    )
    payment = Payment.objects.get(pk=state.sample_ids["payment_ids"][0])
    link = payment.finance_posting_links.first() if hasattr(payment, "finance_posting_links") else None
    # EFRIS guard is tenant based; verify even an existing cashbook row cannot enqueue.
    from apps.finance.models import FinancePostingLink
    posting = FinancePostingLink.objects.filter(
        tenant=bundle["tenant"],
        source_id=str(payment.pk),
    ).select_related("cashbook_entry").first()
    assert posting is not None
    submission, replay = enqueue_efris_submission_for_cashbook_entry(
        posting.cashbook_entry
    )
    assert submission is None
    assert replay is False
    assert not EfrisSubmission.objects.filter(tenant=bundle["tenant"]).exists()


@pytest.mark.django_db
def test_training_workspace_page_banner_seed_and_password_reset():
    bundle = _make_training_bundle()
    client = Client()
    assert client.login(
        username=bundle["user"].email,
        password="TestPass9!",
    )
    session = client.session
    session["staff_tenant_id"] = str(bundle["tenant"].pk)
    session.save()

    page = client.get(reverse("console-org-training"))
    assert page.status_code == 200
    assert b"TRAINING WORKSPACE" in page.content
    assert b"Create retail sample pack" in page.content

    seeded = client.post(
        reverse("console-org-training"),
        {"action": "seed"},
        follow=True,
    )
    assert seeded.status_code == 200
    assert b"Generation 1" in seeded.content
    assert b"Guided exercises" in seeded.content

    bad = client.post(
        reverse("console-org-training"),
        {
            "action": "reset",
            "confirmation": "RESET TRAINING",
            "password": "wrong-password",
        },
    )
    assert bad.status_code == 400
    assert TrainingWorkspaceState.objects.get(
        tenant=bundle["tenant"]
    ).generation == 1

    reset = client.post(
        reverse("console-org-training"),
        {
            "action": "reset",
            "confirmation": "RESET TRAINING",
            "password": "TestPass9!",
        },
        follow=True,
    )
    assert reset.status_code == 200
    assert b"Generation 2" in reset.content


@pytest.mark.django_db
def test_live_workspace_cannot_open_training_controller():
    bundle = _seed_tenant_bundle(
        name="Live Workspace",
        slug="live-workspace-controller",
        user_email="live-workspace-controller@test.local",
    )
    client = Client()
    assert client.login(
        username=bundle["user"].email,
        password="TestPass9!",
    )
    session = client.session
    session["staff_tenant_id"] = str(bundle["tenant"].pk)
    session.save()
    assert client.get(reverse("console-org-training")).status_code == 404
