"""Shared inventory capability decisions for Phase 20.

These checks do not replace per-tenant module and outlet enforcement.
"""
from types import SimpleNamespace

import pytest

from apps.accounts.models import MembershipRole
from apps.staff.services.permissions import (
    membership_can_modify_inventory,
    membership_has_inventory_capability,
)


@pytest.mark.parametrize("capability", ["view", "adjust", "transfer", "request_transfer", "approve_transfer", "count"])
def test_unknown_and_inactive_memberships_fail_closed(capability):
    assert not membership_has_inventory_capability(None, capability)
    for role in (MembershipRole.OWNER, MembershipRole.ACCOUNTANT):
        inactive = SimpleNamespace(role=role, is_active=False)
        assert not membership_has_inventory_capability(inactive, capability)
    active = SimpleNamespace(role=MembershipRole.OWNER, is_active=True)
    assert not membership_has_inventory_capability(active, "delete_everything")


def test_accountants_have_read_only_inventory_access():
    accountant = SimpleNamespace(role=MembershipRole.ACCOUNTANT, is_active=True)
    assert membership_has_inventory_capability(accountant, "view")
    for capability in ("adjust", "transfer", "request_transfer", "approve_transfer", "count"):
        assert not membership_has_inventory_capability(accountant, capability)
    assert not membership_can_modify_inventory(accountant)


def test_storekeeper_can_perform_stock_operations():
    storekeeper = SimpleNamespace(role=MembershipRole.STOREKEEPER, is_active=True)
    assert all(
        membership_has_inventory_capability(storekeeper, action)
        for action in ("view", "adjust", "transfer", "request_transfer", "count")
    )
    assert not membership_has_inventory_capability(storekeeper, "approve_transfer")
    assert membership_can_modify_inventory(storekeeper)


def test_front_desk_does_not_gain_inventory_access():
    front_desk = SimpleNamespace(role=MembershipRole.FRONT_DESK, is_active=True)
    assert not any(
        membership_has_inventory_capability(front_desk, action)
        for action in ("view", "adjust", "transfer", "request_transfer", "approve_transfer", "count")
    )
