"""Separate stock count approval must preserve intervening stock movements."""
from decimal import Decimal
import pytest
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model
from apps.accounts.models import Membership, MembershipRole
from apps.inventory.models import StockBalance, StockCountSession, StockCountStatus, StockMovement
from apps.inventory.services import (
    submit_stock_count_for_review, approve_stock_count_session,
    return_stock_count_for_recount,
)
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_stock_count_requires_a_different_manager_to_post_and_cannot_replay():
    data = _seed_tenant_bundle(
        name="Review Count", slug="review-count", user_email="review-count@example.test",
    )
    worker = get_user_model().objects.create_user(
        email="stock-counter@example.test", password="TestPassword99!",
    )
    counter = Membership.objects.create(
        tenant=data["tenant"], user=worker, role=MembershipRole.STOREKEEPER,
    )
    counter.sites.add(data["site"])
    counter.outlets.add(data["outlet"])
    manager = Membership.objects.get(tenant=data["tenant"], user=data["user"])
    bal = StockBalance.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], menu_item=data["item"],
        quantity=Decimal("12"),
    )
    session = StockCountSession.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], created_by=worker,
    )
    submit_stock_count_for_review(
        session=session, resolved_lines=[
            {"menu_item": data["item"], "counted_quantity": Decimal("10")},
        ], user=worker, membership=counter,
    )
    session.refresh_from_db()
    bal.refresh_from_db()
    assert session.status == StockCountStatus.REVIEW
    assert bal.quantity == Decimal("12")
    assert not StockMovement.objects.filter(tenant=data["tenant"]).exists()
    with pytest.raises(ValidationError, match="manager"):
        approve_stock_count_session(session=session, user=worker, membership=counter)
    # An intervening sale changes the baseline; no approval may undo it.
    bal.quantity = Decimal("11")
    bal.save(update_fields=["quantity"])
    with pytest.raises(ValidationError, match="changed since counting"):
        approve_stock_count_session(session=session, user=data["user"], membership=manager)
    bal.refresh_from_db()
    assert bal.quantity == Decimal("11")
    assert not StockMovement.objects.filter(tenant=data["tenant"]).exists()
    with pytest.raises(ValidationError, match="reason"):
        return_stock_count_for_recount(
            session=session, user=data["user"], membership=manager, reason="",
        )
    return_stock_count_for_recount(
        session=session, user=data["user"], membership=manager,
        reason="Sale occurred after the stock take.",
    )
    session.refresh_from_db()
    assert session.status == StockCountStatus.DRAFT
    assert not session.lines.exists()
    submit_stock_count_for_review(
        session=session, resolved_lines=[
            {"menu_item": data["item"], "counted_quantity": Decimal("9")},
        ], user=worker, membership=counter,
    )
    approve_stock_count_session(session=session, user=data["user"], membership=manager)
    session.refresh_from_db()
    bal.refresh_from_db()
    assert session.status == StockCountStatus.COMPLETED
    assert session.approved_by_id == data["user"].id
    assert bal.quantity == Decimal("9")
    assert StockMovement.objects.get(tenant=data["tenant"]).quantity_change == Decimal("-2")
    with pytest.raises(ValidationError, match="submitted"):
        approve_stock_count_session(session=session, user=data["user"], membership=manager)


@pytest.mark.django_db
def test_stock_count_cannot_approve_own_submission():
    data = _seed_tenant_bundle(
        name="Own Count", slug="own-count", user_email="own-count@example.test",
    )
    manager = Membership.objects.get(tenant=data["tenant"], user=data["user"])
    session = StockCountSession.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], created_by=data["user"],
    )
    submit_stock_count_for_review(
        session=session, resolved_lines=[
            {"menu_item": data["item"], "counted_quantity": Decimal("1")},
        ], user=data["user"], membership=manager,
    )
    with pytest.raises(ValidationError, match="different manager"):
        approve_stock_count_session(session=session, user=data["user"], membership=manager)
    assert session.lines.count() == 1



@pytest.mark.django_db
def test_net_zero_stock_movements_still_invalidate_review_snapshot():
    from apps.inventory.models import StockMovement, StockReason
    data = _seed_tenant_bundle(
        name="Net Zero Count", slug="net-zero-count", user_email="net-zero-count@example.test",
    )
    manager = Membership.objects.get(tenant=data["tenant"], user=data["user"])
    other = get_user_model().objects.create_user(
        email="net-zero-counter@example.test", password="TestPassword99!",
    )
    worker = Membership.objects.create(
        tenant=data["tenant"], user=other, role=MembershipRole.STOREKEEPER,
    )
    worker.sites.add(data["site"])
    worker.outlets.add(data["outlet"])
    balance = StockBalance.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], menu_item=data["item"],
        quantity=Decimal("5"),
    )
    session = StockCountSession.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], created_by=other,
    )
    submit_stock_count_for_review(
        session=session, user=other, membership=worker,
        resolved_lines=[{"menu_item": data["item"], "counted_quantity": "4"}],
    )
    # A sale and a refund net to zero; quantity-only checks would miss both.
    StockMovement.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], menu_item=data["item"],
        quantity_change=Decimal("-1"), reason=StockReason.SALE, created_by=other,
    )
    StockMovement.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], menu_item=data["item"],
        quantity_change=Decimal("1"), reason=StockReason.RECEIVE, created_by=other,
    )
    with pytest.raises(ValidationError, match="changed since counting"):
        approve_stock_count_session(session=session, user=data["user"], membership=manager)
    balance.refresh_from_db()
    assert balance.quantity == Decimal("5")
    assert not StockMovement.objects.filter(
        tenant=data["tenant"], reason=StockReason.PHYSICAL_COUNT,
    ).exists()



@pytest.mark.django_db
def test_storekeeper_cannot_bypass_review_using_direct_completion_service():
    from apps.inventory.services import complete_stock_count_session
    data = _seed_tenant_bundle(
        name="Count Approval Guard", slug="count-approval-guard",
        user_email="count-approval-guard@example.test",
    )
    counter_user = get_user_model().objects.create_user(
        email="guard-counter@example.test", password="TestPassword99!",
    )
    counter = Membership.objects.create(
        tenant=data["tenant"], user=counter_user, role=MembershipRole.STOREKEEPER,
    )
    counter.sites.add(data["site"])
    counter.outlets.add(data["outlet"])
    balance = StockBalance.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], menu_item=data["item"],
        quantity=Decimal("6"),
    )
    session = StockCountSession.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], created_by=counter_user,
    )
    with pytest.raises(ValidationError, match="authorized manager"):
        complete_stock_count_session(
            session=session, user=counter_user, membership=counter,
            resolved_lines=[{"menu_item": data["item"], "counted_quantity": "1"}],
        )
    balance.refresh_from_db()
    session.refresh_from_db()
    assert balance.quantity == Decimal("6")
    assert session.status == StockCountStatus.DRAFT
    assert not session.lines.exists()
    assert not StockMovement.objects.filter(tenant=data["tenant"]).exists()
