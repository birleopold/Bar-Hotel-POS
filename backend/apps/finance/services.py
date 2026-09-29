from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    CashbookEntry,
    FinanceCategory,
    FinanceCategoryKind,
    FinancePostingLink,
    FinancePostingSource,
)

SYSTEM_POS_INCOME_CATEGORY = "POS Sales"
SYSTEM_POS_REFUND_CATEGORY = "POS Refunds"
SYSTEM_FOLIO_INCOME_CATEGORY = "Guest Folio Payments"
SYSTEM_PURCHASE_EXPENSE_CATEGORY = "Stock Purchases"


def _system_category_for_kind(*, tenant_id, kind: str, default_name: str) -> FinanceCategory:
    category = (
        FinanceCategory.objects.filter(
            tenant_id=tenant_id,
            kind=kind,
            is_active=True,
            name__iexact=default_name,
        )
        .order_by("name")
        .first()
    )
    if category:
        return category
    return FinanceCategory.objects.create(
        tenant_id=tenant_id,
        name=default_name,
        kind=kind,
        sort_order=999,
        is_active=True,
    )


@transaction.atomic
def post_cashbook_for_source(
    *,
    tenant_id,
    source_type: str,
    source_id: str,
    kind: str,
    amount: Decimal,
    site=None,
    reference: str = "",
    note: str = "",
    created_by=None,
    transaction_date=None,
    default_category_name: str | None = None,
    enqueue_efris: bool = True,
) -> tuple[CashbookEntry | None, bool]:
    """
    Idempotently post one operational event to one cashbook entry.
    """
    if amount <= 0:
        return None, False
    existing = (
        FinancePostingLink.objects.select_related("cashbook_entry")
        .filter(tenant_id=tenant_id, source_type=source_type, source_id=source_id)
        .first()
    )
    if existing is not None:
        return existing.cashbook_entry, True

    category = _system_category_for_kind(
        tenant_id=tenant_id,
        kind=kind,
        default_name=default_category_name or (
            SYSTEM_POS_INCOME_CATEGORY
            if kind == FinanceCategoryKind.INCOME
            else SYSTEM_PURCHASE_EXPENSE_CATEGORY
        ),
    )
    entry = CashbookEntry.objects.create(
        tenant_id=tenant_id,
        category=category,
        site=site,
        amount=amount.quantize(Decimal("0.01")),
        transaction_date=(transaction_date or timezone.localdate()),
        reference=(reference or "")[:64],
        note=(note or "")[:1000],
        created_by=created_by,
    )
    try:
        FinancePostingLink.objects.create(
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            cashbook_entry=entry,
        )
    except IntegrityError:
        # Parallel write won race; reuse canonical posting.
        existing = (
            FinancePostingLink.objects.select_related("cashbook_entry")
            .filter(tenant_id=tenant_id, source_type=source_type, source_id=source_id)
            .first()
        )
        if existing is not None:
            entry.delete()
            return existing.cashbook_entry, True
        raise
    from apps.integrations.services import enqueue_efris_submission_for_cashbook_entry

    if enqueue_efris:
        enqueue_efris_submission_for_cashbook_entry(entry)
    return entry, False


def post_pos_payment_income(*, payment, order, user) -> tuple[CashbookEntry | None, bool]:
    return post_cashbook_for_source(
        tenant_id=order.tenant_id,
        source_type=FinancePostingSource.POS_PAYMENT,
        source_id=str(payment.id),
        kind=FinanceCategoryKind.INCOME,
        amount=payment.amount,
        site=order.outlet.site,
        reference=order.bill_reference,
        note=f"Auto-posted from POS payment {payment.id}",
        created_by=user,
        transaction_date=payment.created_at.date(),
    )


def post_pos_refund_expense(*, refund, order, user) -> tuple[CashbookEntry | None, bool]:
    return post_cashbook_for_source(
        tenant_id=order.tenant_id,
        source_type=FinancePostingSource.POS_REFUND,
        source_id=str(refund.id),
        kind=FinanceCategoryKind.EXPENSE,
        amount=refund.amount,
        site=order.outlet.site,
        reference=order.bill_reference,
        note=f"Auto-posted from POS refund {refund.id}",
        created_by=user,
        transaction_date=refund.created_at.date(),
        default_category_name=SYSTEM_POS_REFUND_CATEGORY,
        enqueue_efris=False,
    )


def post_folio_payment_income(*, payment, user) -> tuple[CashbookEntry | None, bool]:
    folio = payment.folio
    return post_cashbook_for_source(
        tenant_id=folio.tenant_id,
        source_type=FinancePostingSource.FOLIO_PAYMENT,
        source_id=str(payment.id),
        kind=FinanceCategoryKind.INCOME,
        amount=payment.amount,
        site=folio.site,
        reference=(payment.reference or str(folio.id))[:64],
        note=f"Auto-posted from guest folio payment {payment.id}",
        created_by=user,
        transaction_date=payment.created_at.date(),
        default_category_name=SYSTEM_FOLIO_INCOME_CATEGORY,
    )


def post_purchase_receive_expense_from_movement(
    *,
    movement,
    po,
    line,
    quantity,
    user,
) -> tuple[CashbookEntry | None, bool]:
    if line.unit_cost is None or line.unit_cost <= 0:
        return None, False
    amount = (quantity * line.unit_cost).quantize(Decimal("0.01"))
    return post_cashbook_for_source(
        tenant_id=po.tenant_id,
        source_type=FinancePostingSource.PURCHASE_RECEIVE_MOVEMENT,
        source_id=str(movement.id),
        kind=FinanceCategoryKind.EXPENSE,
        amount=amount,
        site=po.outlet.site,
        reference=(po.reference or str(po.id))[:64],
        note=f"Auto-posted from PO receive movement {movement.id}",
        created_by=user,
        transaction_date=movement.created_at.date(),
    )
