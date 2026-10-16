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
