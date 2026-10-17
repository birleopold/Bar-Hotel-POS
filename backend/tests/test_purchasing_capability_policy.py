"""Phase 20 purchasing permissions: stock receipt is not finance permission."""
from types import SimpleNamespace

import pytest

from apps.accounts.models import MembershipRole
from apps.staff.services.permissions import membership_has_purchasing_capability


@pytest.mark.parametrize("action", ["view", "receive", "manage", "supplier_payment"])
def test_purchasing_rejects_missing_and_inactive_staff(action):
    assert not membership_has_purchasing_capability(None, action)
    assert not membership_has_purchasing_capability(
        SimpleNamespace(is_active=False, role=MembershipRole.OWNER), action,
    )


def test_storekeeper_receives_without_supplier_payment_or_order_management():
    worker = SimpleNamespace(is_active=True, role=MembershipRole.STOREKEEPER)
    assert membership_has_purchasing_capability(worker, "view")
    assert membership_has_purchasing_capability(worker, "receive")
    assert not membership_has_purchasing_capability(worker, "manage")
    assert not membership_has_purchasing_capability(worker, "supplier_payment")


def test_accountant_cannot_receive_or_change_supplier_finance():
    accountant = SimpleNamespace(is_active=True, role=MembershipRole.ACCOUNTANT)
    assert membership_has_purchasing_capability(accountant, "view")
    for action in ("receive", "manage", "supplier_payment"):
        assert not membership_has_purchasing_capability(accountant, action)


def test_owner_can_perform_purchasing_actions_and_unknown_denied():
    owner = SimpleNamespace(is_active=True, role=MembershipRole.OWNER)
    assert all(
        membership_has_purchasing_capability(owner, action)
        for action in ("view", "receive", "manage", "supplier_payment")
    )
    assert not membership_has_purchasing_capability(owner, "write_off_debt")


@pytest.mark.parametrize("action,allowed_storekeeper", [
    ("receive", True),
    ("record_payment", False),
    ("link_payment", False),
    ("record_invoice", False),
    ("confirm_cost", False),
    ("create", False),
    ("partial_update", False),
])
def test_purchase_api_actions_use_correct_role_capability(action, allowed_storekeeper):
    from apps.purchasing.views import PurchasingActionPermission, PurchaseOrderViewSet

    permission = PurchasingActionPermission()
    assert PurchasingActionPermission in PurchaseOrderViewSet.permission_classes
    request = SimpleNamespace(
        method="POST", tenant_membership=SimpleNamespace(
            is_active=True, role=MembershipRole.STOREKEEPER,
        ),
    )
    view = SimpleNamespace(action=action)
    assert permission.has_permission(request, view) is allowed_storekeeper
    request.tenant_membership.role = MembershipRole.OWNER
    assert permission.has_permission(request, view)
    request.tenant_membership.is_active = False
    assert not permission.has_permission(request, view)


def test_supplier_api_mutations_require_manager_and_accountant_stays_read_only():
    from apps.purchasing.views import PurchasingActionPermission, SupplierViewSet

    permission = PurchasingActionPermission()
    assert PurchasingActionPermission in SupplierViewSet.permission_classes
    membership = SimpleNamespace(is_active=True, role=MembershipRole.STOREKEEPER)
    request = SimpleNamespace(method="PATCH", tenant_membership=membership)
    assert not permission.has_permission(request, SimpleNamespace(action="partial_update"))
    membership.role = MembershipRole.SITE_MANAGER
    assert permission.has_permission(request, SimpleNamespace(action="partial_update"))
    membership.role = MembershipRole.ACCOUNTANT
    request.method = "GET"
    assert permission.has_permission(request, SimpleNamespace(action="list"))
    request.method = "POST"
    assert not permission.has_permission(request, SimpleNamespace(action="create"))
