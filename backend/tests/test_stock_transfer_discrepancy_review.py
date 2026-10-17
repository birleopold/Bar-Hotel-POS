"""F3 discrepancy review is independent, scoped and stock-neutral."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import (
    verify_stock_transfer_receipt, review_stock_transfer_discrepancy,
)
from tests.test_stock_transfer_receipt_confirmation import make_transfer


def manager_for(setup, destination, slug):
    user = get_user_model().objects.create_user(
        email=f"reviewer-{slug}@example.test", password="TestPass999!",
    )
    membership = Membership.objects.create(
        tenant=setup["tenant"], user=user, role=MembershipRole.OUTLET_MANAGER,
    )
    membership.sites.add(setup["site"])
    membership.outlets.add(destination)
    return user, membership


@pytest.mark.django_db
def test_independent_manager_review_does_not_change_inventory_or_replay():
    setup, destination, receiver, receiver_membership, origin, receipt = make_transfer("review-case")
    verify_stock_transfer_receipt(
        receipt=receipt, membership=receiver_membership, user=receiver,
        received_quantity="2", note="Two units short in delivered box.",
    )
    reviewer, manager = manager_for(setup, destination, "independent")
    before = StockBalance.objects.get(outlet=destination, menu_item=setup["item"]).quantity
    movements = StockMovement.objects.filter(transfer_batch=receipt.transfer_batch).count()
    reviewed = review_stock_transfer_discrepancy(
        receipt=receipt, membership=manager, user=reviewer,
        review_action="needs_count", note="Ask another worker for a blind recount.",
    )
    assert reviewed.review_action == "needs_count"
    assert reviewed.reviewed_by_id == reviewer.pk
    assert reviewed.reviewed_at is not None
    assert reviewed.review_note.startswith("Ask another")
    assert StockBalance.objects.get(outlet=destination, menu_item=setup["item"]).quantity == before
    assert StockMovement.objects.filter(transfer_batch=receipt.transfer_batch).count() == movements == 2
    with pytest.raises(ValidationError, match="already"):
        review_stock_transfer_discrepancy(
            receipt=receipt, membership=manager, user=reviewer,
            review_action="documented", note="Attempt to overwrite first review.",
        )


@pytest.mark.django_db
def test_review_requires_a_dispute_and_independent_manager():
    setup, destination, receiver, receiver_membership, origin, receipt = make_transfer("review-roles")
    reviewer, manager = manager_for(setup, destination, "roles")
    with pytest.raises(ValidationError, match="discrepancy"):
        review_stock_transfer_discrepancy(
            receipt=receipt, membership=manager, user=reviewer,
            review_action="needs_count", note="Please arrange a recount.",
        )
    verify_stock_transfer_receipt(
        receipt=receipt, membership=receiver_membership, user=receiver,
        received_quantity="3", note="A unit was missing.",
    )
    for user, membership in (
        (setup["user"], Membership.objects.get(user=setup["user"], tenant=setup["tenant"])),
        (receiver, receiver_membership),
    ):
        with pytest.raises(ValidationError):
            review_stock_transfer_discrepancy(
                receipt=receipt, membership=membership, user=user,
                review_action="needs_count", note="Follow-up investigation.",
            )
    with pytest.raises(ValidationError, match="manager"):
        review_stock_transfer_discrepancy(
            receipt=receipt, membership=receiver_membership, user=reviewer,
            review_action="needs_count", note="Not a manager reviewing.",
        )
    receipt.refresh_from_db()
    assert receipt.reviewed_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("action,note", [
    ("unknown", "This explanation has enough characters."),
    ("needs_count", "short"),
    ("documented", ""),
    ("documented", "x" * 513),
])
def test_invalid_review_keeps_discrepancy_pending(action, note):
    setup, destination, receiver, receiver_membership, origin, receipt = make_transfer("review-invalid")
    verify_stock_transfer_receipt(
        receipt=receipt, membership=receiver_membership, user=receiver,
        received_quantity="0", note="Nothing arrived in destination.",
    )
    reviewer, manager = manager_for(setup, destination, "invalid")
    with pytest.raises(ValidationError):
        review_stock_transfer_discrepancy(
            receipt=receipt, membership=manager, user=reviewer,
            review_action=action, note=note,
        )
    receipt.refresh_from_db()
    assert receipt.review_action == ""
    assert receipt.reviewed_at is None


@pytest.mark.django_db
def test_other_tenant_and_outlet_denied_review():
    setup, destination, receiver, receiver_membership, origin, receipt = make_transfer("review-scoped")
    verify_stock_transfer_receipt(
        receipt=receipt, membership=receiver_membership, user=receiver,
        received_quantity="1", note="Counted one piece only.",
    )
    unrelated_user, unrelated_membership = manager_for(setup, destination, "scoped")
    unrelated_membership.outlets.clear()
    # Separate assignment to a different outlet of the same site.
    unrelated_membership.outlets.add(setup["outlet"])
    with pytest.raises(ValidationError, match="destination"):
        review_stock_transfer_discrepancy(
            receipt=receipt, membership=unrelated_membership, user=unrelated_user,
            review_action="needs_count", note="Investigate wrong outlet.",
        )
