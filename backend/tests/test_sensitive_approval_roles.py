"""Phase 21 approver eligibility: not yet a transaction-bound manager approval."""
from types import SimpleNamespace
import pytest

from apps.accounts.models import MembershipRole
from apps.staff.services.permissions import (
    membership_can_approve_refunds,
    membership_can_approve_sensitive_action,
)


@pytest.mark.parametrize("action", [
    "refund", "retail_line_refund", "discount", "void",
    "reopen", "stock_write_off", "price_override", "withdrawal",
])
def test_manager_authority_requires_active_eligible_member(action):
    manager = SimpleNamespace(role=MembershipRole.OUTLET_MANAGER, is_active=True)
    assert membership_can_approve_sensitive_action(manager, action)
    assert not membership_can_approve_sensitive_action(None, action)
    assert not membership_can_approve_sensitive_action(
        SimpleNamespace(role=MembershipRole.OUTLET_MANAGER, is_active=False), action,
    )
    assert not membership_can_approve_sensitive_action(
        SimpleNamespace(role=MembershipRole.SERVER, is_active=True), action,
    )


def test_unknown_sensitive_action_fails_closed_and_refund_compatibility():
    owner = SimpleNamespace(role=MembershipRole.OWNER, is_active=True)
    accountant = SimpleNamespace(role=MembershipRole.ACCOUNTANT, is_active=True)
    assert not membership_can_approve_sensitive_action(owner, "any")
    assert membership_can_approve_refunds(owner)
    assert not membership_can_approve_refunds(accountant)
