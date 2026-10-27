"""Customer price books layered onto the existing retail order-line engine."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.catalog.models import MenuItem
from apps.pos.models import (
    CustomerPriceBookAssignment,
    Order,
    OrderLine,
    OrderStatus,
    PriceBookRule,
)
from apps.tenants.models import OutletType

from .pricing import line_tax, line_total, recalculate_order_totals


RETAIL_OUTLET_TYPES = {OutletType.RETAIL, OutletType.SUPERMARKET}
ORDINARY_PRICE_SOURCES = {
    "menu", "barcode", "plu", "weighted", "package", "serial", "alternate",
}


def _normalized_quantity(quantity) -> Decimal:
    try:
        qty = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"quantity": "Enter a valid quantity."}) from exc
    if not qty.is_finite() or qty <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    return qty


def qualifying_customer_price_rule(
    *,
    tenant_id,
    outlet_id,
    customer_id,
    menu_item_id,
    quantity,
    at=None,
) -> PriceBookRule | None:
    """Resolve one assigned customer price tier; base menu price remains fallback."""
    if not customer_id:
        return None
    qty = _normalized_quantity(quantity)
    now = at or timezone.now()
    assignment = (
        CustomerPriceBookAssignment.objects.select_related("price_book", "customer")
        .filter(
            tenant_id=tenant_id,
            customer_id=customer_id,
            customer__merged_into__isnull=True,
            price_book__is_active=True,
        )
        .filter(
            Q(price_book__starts_at__isnull=True) | Q(price_book__starts_at__lte=now),
            Q(price_book__ends_at__isnull=True) | Q(price_book__ends_at__gte=now),
        )
        .first()
    )
    if assignment is None:
        return None
    book = assignment.price_book
    if book.outlets.exists() and not book.outlets.filter(pk=outlet_id).exists():
        return None
    item = (
        MenuItem.objects.filter(
            tenant_id=tenant_id,
            pk=menu_item_id,
            is_active=True,
        )
        .only("id", "category_id", "product_family_id", "brand")
        .first()
    )
    if item is None:
        return None

    target_filter = Q(menu_item_id=item.pk)
    if item.product_family_id:
        target_filter |= Q(product_family_id=item.product_family_id)
    if item.brand:
        target_filter |= Q(brand__iexact=item.brand)
    target_filter |= Q(category_id=item.category_id)

    candidates = list(
        PriceBookRule.objects.filter(
            tenant_id=tenant_id,
            price_book=book,
            is_active=True,
            minimum_quantity__lte=qty,
        )
        .filter(target_filter)
        .select_related("menu_item", "product_family", "category")
    )
    if not candidates:
        return None

    def priority(rule):
        if rule.menu_item_id == item.pk:
            specificity = 4
        elif item.product_family_id and rule.product_family_id == item.product_family_id:
            specificity = 3
        elif rule.brand and item.brand and rule.brand.casefold() == item.brand.casefold():
            specificity = 2
        elif rule.category_id == item.category_id:
            specificity = 1
        else:
            specificity = 0
        return (
            specificity,
            rule.minimum_quantity,
            -rule.unit_price,
            str(rule.pk),
        )

    return max(candidates, key=priority)


def _modifier_delta(line: OrderLine) -> Decimal:
    total = Decimal("0")
    for row in line.modifiers_snapshot or []:
        try:
            total += Decimal(str(row.get("price_delta") or "0"))
        except (InvalidOperation, TypeError, ValueError, AttributeError):
            continue
    return total


def _line_is_repriceable(line: OrderLine) -> bool:
    return bool(
        line.menu_item_id
        and not line.is_voided
        and line.pricing_source in ORDINARY_PRICE_SOURCES
        and line.line_discount_amount == Decimal("0")
        and line.line_discount_percent is None
    )


def apply_customer_price_to_locked_line(
    *,
    order: Order,
    line: OrderLine,
    base_unit_price: Decimal | None = None,
) -> tuple[OrderLine, bool]:
    """Apply/clear one price-book override on already locked order + line rows."""
    if not _line_is_repriceable(line):
        return line, False
    if order.outlet.outlet_type not in RETAIL_OUTLET_TYPES:
        return line, False

    base = (
        line.price_book_base_unit_price
        if line.price_book_rule_id and line.price_book_base_unit_price is not None
        else base_unit_price
        if base_unit_price is not None
        else line.unit_price
    )
    base = Decimal(str(base)).quantize(Decimal("0.01"))
    rule = qualifying_customer_price_rule(
        tenant_id=order.tenant_id,
        outlet_id=order.outlet_id,
        customer_id=order.customer_id,
        menu_item_id=line.menu_item_id,
        quantity=line.quantity,
    )

    new_price = rule.unit_price if rule is not None else base
    new_rule_id = rule.pk if rule is not None else None
    new_base = base if rule is not None else None
    if (
        line.unit_price == new_price
        and line.price_book_rule_id == new_rule_id
        and line.price_book_base_unit_price == new_base
    ):
        return line, False

    before = {
        "unit_price": str(line.unit_price),
        "price_book_rule_id": str(line.price_book_rule_id) if line.price_book_rule_id else None,
    }
    line.unit_price = new_price
    line.price_book_rule = rule
    line.price_book_base_unit_price = new_base
    effective_unit = line.unit_price + _modifier_delta(line)
    line.line_total = line_total(line.quantity, effective_unit)
    line.tax_amount = line_tax(line.line_total, line.menu_item.tax_rate_percent)
    line.save(update_fields=[
        "unit_price",
        "price_book_rule",
        "price_book_base_unit_price",
        "line_total",
        "tax_amount",
        "updated_at",
    ])
    return line, True


@transaction.atomic
def reprice_open_retail_order_for_customer(*, order: Order, user=None) -> tuple[int, bool]:
    """Reprice normal lines after customer link changes; never mutate paid/deposit history."""
    locked = (
        Order.objects.select_for_update(of=("self",))
        .select_related("outlet", "customer")
        .get(pk=order.pk)
    )
    if locked.outlet.outlet_type not in RETAIL_OUTLET_TYPES:
        return 0, False
    if locked.status != OrderStatus.OPEN or locked.is_paid:
        return 0, True
    if locked.payments.exists():
        return 0, True
    if locked.applied_promotion_id or locked.discount_amount:
        return 0, True

    changed = 0
    lines = list(
        locked.lines.select_for_update(of=("self",))
        .select_related("menu_item")
        .filter(is_voided=False, menu_item__isnull=False)
        .order_by("sort_order")
    )
    for line in lines:
        _line, did_change = apply_customer_price_to_locked_line(
            order=locked,
            line=line,
        )
        changed += int(did_change)
    if changed:
        recalculate_order_totals(locked)
        log_audit(
            tenant_id=locked.tenant_id,
            user_id=user.pk if user else None,
            action="order.customer_price_book_repriced",
            entity_type="order",
            entity_id=str(locked.pk),
            payload={
                "customer_id": str(locked.customer_id) if locked.customer_id else None,
                "changed_lines": changed,
            },
        )
    return changed, False
