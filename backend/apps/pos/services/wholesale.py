"""Opt-in retail wholesale price snapshots; ordinary sales remain untouched."""
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log_audit
from apps.accounts.models import MembershipRole
from apps.catalog.models import MenuItem
from apps.pos.models import Order, OrderLine, OrderStatus, WholesalePriceRule
from apps.pos.services.pricing import line_total, line_tax, recalculate_order_totals
from apps.tenants.models import OutletType

MANAGERS = frozenset({
    MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
})


def manager_allowed(membership, tenant_id, outlet_id):
    from apps.access.outlets import outlet_belongs_to_membership
    return bool(membership and membership.is_active
                and membership.tenant_id == tenant_id and membership.role in MANAGERS
                and outlet_belongs_to_membership(membership, outlet_id))


def qualifying_rule(*, tenant_id, outlet_id, menu_item_id, quantity, at=None):
    now = at or timezone.now()
    return WholesalePriceRule.objects.filter(
        tenant_id=tenant_id, outlet_id=outlet_id, menu_item_id=menu_item_id,
        is_active=True, minimum_quantity__lte=quantity,
    ).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now)).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gte=now)
    ).order_by("-minimum_quantity", "unit_price", "pk").first()


@transaction.atomic
def save_wholesale_tier(*, tenant, outlet, item_id, quantity, price,
                        membership, user, start=None, end=None, active=True):
    if (outlet.site.tenant_id != tenant.pk
            or outlet.outlet_type not in {OutletType.RETAIL, OutletType.SUPERMARKET}
            or not manager_allowed(membership, tenant.pk, outlet.pk)
            or membership.user_id != user.pk):
        raise ValidationError({"detail": "Only a retail manager of this section can set wholesale rates."})
    item = MenuItem.objects.filter(pk=item_id, tenant=tenant, is_active=True).first()
    if item is None:
        raise ValidationError({"item": "Select an active product in your business."})
    # This uses the same product catalog eligibility as the register; no hidden cross-section SKU.
    from apps.pos.services.menu import menu_items_for_outlet_queryset
    if not menu_items_for_outlet_queryset(tenant.pk, outlet.pk).filter(pk=item.pk).exists():
        raise ValidationError({"item": "Product is not sold in this section."})
    try:
        qty, cost = Decimal(str(quantity)), Decimal(str(price))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValidationError({"price": "Enter valid quantity and price."}) from exc
    if not qty.is_finite() or qty <= 0 or qty > 9999999 or qty != qty.quantize(Decimal("0.001")):
        raise ValidationError({"quantity": "Use a positive threshold with at most three decimal places."})
    if not cost.is_finite() or cost < 0 or cost > Decimal("9999999999.99") or cost != cost.quantize(Decimal("0.01")):
        raise ValidationError({"price": "Use a nonnegative amount with two decimal places."})
    if start and end and end <= start:
        raise ValidationError({"end": "End must be later than the start."})
    rule, created = WholesalePriceRule.objects.select_for_update().get_or_create(
        tenant=tenant, outlet=outlet, menu_item=item, minimum_quantity=qty,
        defaults={"unit_price": cost, "starts_at": start, "ends_at": end,
                  "is_active": bool(active), "created_by": user},
    )
    if not created and (rule.unit_price, rule.starts_at, rule.ends_at, rule.is_active) != (cost, start, end, bool(active)):
        rule.unit_price, rule.starts_at, rule.ends_at, rule.is_active = cost, start, end, bool(active)
        rule.save(update_fields=["unit_price", "starts_at", "ends_at", "is_active", "updated_at"])
    log_audit(tenant_id=tenant.pk, user_id=user.pk, action="retail.wholesale_price_configured",
              entity_type="wholesale_price_rule", entity_id=str(rule.pk),
              payload={"outlet_id": str(outlet.pk), "product_id": str(item.pk),
                       "minimum_quantity": str(qty), "unit_price": str(cost), "active": bool(active)})
    return rule


@transaction.atomic
def apply_wholesale_tier(*, order, line_id, membership, user):
    locked = Order.objects.select_for_update().select_related("outlet", "customer").get(pk=order.pk)
    if (locked.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}
            or not manager_allowed(membership, locked.tenant_id, locked.outlet_id)
            or membership.user_id != user.pk):
        raise ValidationError({"detail": "A manager of this retail section must approve wholesale pricing."})
    if (locked.status != OrderStatus.OPEN or locked.is_paid or locked.customer_id is None
            or locked.customer.merged_into_id or locked.applied_promotion_id
            or locked.discount_amount):
        raise ValidationError({"order": "Wholesale prices require an identified customer and an open, unpromoted sale."})
    if locked.payments.exists():
        raise ValidationError({"order": "Apply price rules before taking any deposit or payment."})
    line = OrderLine.objects.select_for_update().select_related("menu_item").filter(
        order=locked, pk=line_id, is_voided=False, menu_item__isnull=False,
    ).first()
    if (line is None or line.modifiers_snapshot or line.line_discount_amount
            or line.line_discount_percent):
        raise ValidationError({"line": "Choose a normal product line without discounts or modifiers."})
    rule = qualifying_rule(tenant_id=locked.tenant_id, outlet_id=locked.outlet_id,
                           menu_item_id=line.menu_item_id, quantity=line.quantity)
    if rule is None:
        raise ValidationError({"quantity": "No active wholesale tier covers the ordered quantity."})
    if line.pricing_source == "wholesale" and line.unit_price == rule.unit_price:
        return line, True
    original = line.unit_price
    previous_price_book_rule_id = line.price_book_rule_id
    line.unit_price = rule.unit_price
    line.line_total = line_total(line.quantity, rule.unit_price)
    line.tax_amount = line_tax(line.line_total, line.menu_item.tax_rate_percent)
    line.pricing_source = "wholesale"
    line.price_book_rule = None
    line.price_book_base_unit_price = None
    line.save(update_fields=[
        "unit_price", "line_total", "tax_amount", "pricing_source",
        "price_book_rule", "price_book_base_unit_price", "updated_at",
    ])
    recalculate_order_totals(locked)
    log_audit(tenant_id=locked.tenant_id, user_id=user.pk,
              action="retail.wholesale_price_applied", entity_type="order_line",
              entity_id=str(line.pk), payload={
                  "order_id": str(locked.pk), "customer_id": str(locked.customer_id),
                  "price_rule_id": str(rule.pk), "previous_unit_price": str(original),
                  "previous_customer_price_book_rule_id": (
                      str(previous_price_book_rule_id) if previous_price_book_rule_id else None
                  ),
                  "unit_price": str(rule.unit_price), "quantity": str(line.quantity),
              })
    return line, False
