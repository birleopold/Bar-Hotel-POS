from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import CommissionRule, Membership
from apps.audit.services import log_audit
from apps.pos.models import Order, OrderLine


MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _line_net_revenue(order: Order, line: OrderLine) -> Decimal:
    gross = _money(line.line_total)
    subtotal = _money(order.subtotal)
    discount = _money(order.discount_amount)
    if gross <= 0 or subtotal <= 0 or discount <= 0:
        return gross
    allocated = (discount * gross / subtotal).quantize(MONEY, rounding=ROUND_HALF_UP)
    return max(ZERO, gross - min(gross, allocated))


def _rule_specificity(rule: CommissionRule) -> tuple[int, int, int, int, str]:
    return (
        int(rule.membership_id is not None)
        + int(rule.menu_item_id is not None)
        + int(rule.category_id is not None),
        int(rule.membership_id is not None),
        int(rule.menu_item_id is not None),
        int(rule.category_id is not None),
        str(rule.pk),
    )


def _matching_rule(*, rules, membership, line):
    category_id = (
        line.menu_item.category_id
        if line.menu_item_id and getattr(line.menu_item, "category_id", None)
        else None
    )
    matching = []
    for rule in rules:
        if rule.membership_id and (
            membership is None or rule.membership_id != membership.pk
        ):
            continue
        if rule.menu_item_id and rule.menu_item_id != line.menu_item_id:
            continue
        if rule.category_id and rule.category_id != category_id:
            continue
        matching.append(rule)
    if not matching:
        return None
    return max(matching, key=_rule_specificity)


@transaction.atomic
def snapshot_order_commissions(*, order: Order, settled_at=None) -> int:
    """Freeze worker attribution and commission math once at full settlement."""
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if not locked.is_paid and locked.status != "closed":
        return 0
    settled_at = settled_at or timezone.now()
    operating_date = timezone.localtime(settled_at).date()

    membership = None
    if locked.created_by_id:
        membership = Membership.objects.filter(
            tenant_id=locked.tenant_id,
            user_id=locked.created_by_id,
        ).first()

    rules = list(
        CommissionRule.objects.filter(
            tenant_id=locked.tenant_id,
            is_active=True,
        )
        .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=operating_date))
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=operating_date))
        .select_related("membership", "menu_item", "category")
    )
    lines = list(
        OrderLine.objects.select_for_update(of=("self",))
        .filter(order=locked, is_voided=False)
        .select_related("menu_item", "menu_item__category")
        .order_by("sort_order", "created_at")
    )
    updated = 0
    for line in lines:
        if line.commission_settled_at_snapshot is not None:
            continue
        base = _line_net_revenue(locked, line)
        rule = _matching_rule(rules=rules, membership=membership, line=line)
        rate = _money(rule.rate_percent if rule else ZERO)
        amount = (base * rate / Decimal("100")).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
        line.sales_attributed_membership = membership
        line.commission_rule_name_snapshot = rule.name if rule else ""
        line.commission_base_snapshot = base
        line.commission_rate_percent_snapshot = rate
        line.commission_amount_snapshot = amount
        line.commission_settled_at_snapshot = settled_at
        line.save(
            update_fields=[
                "sales_attributed_membership",
                "commission_rule_name_snapshot",
                "commission_base_snapshot",
                "commission_rate_percent_snapshot",
                "commission_amount_snapshot",
                "commission_settled_at_snapshot",
                "updated_at",
            ]
        )
        updated += 1

    if updated:
        log_audit(
            tenant_id=locked.tenant_id,
            user_id=locked.created_by_id,
            action="commission.sale_snapshotted",
            entity_type="order",
            entity_id=str(locked.pk),
            payload={
                "line_count": updated,
                "attributed_membership_id": str(membership.pk) if membership else "",
                "settled_at": settled_at.isoformat(),
            },
            source="pos",
        )
    return updated
