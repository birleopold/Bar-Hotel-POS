from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import Membership
from apps.audit.services import log_audit
from apps.catalog.models import (
    MenuItem,
    Promotion,
    ServiceOffering,
    ServiceOfferingOption,
    SupermarketSkuProfile,
    WeightedPricingMode,
)
from apps.inventory.models import StockMovement, StockReason
from apps.inventory.services import apply_manual_stock_change
from apps.lodging.models import Folio, FolioStatus
from apps.pos.models import (
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    PaymentMethod,
    PosShift,
    PosShiftStatus,
    Refund,
    SupermarketLineReturn,
    Table,
)
from apps.tenants.models import Outlet, OutletType, Tenant, TenantSettings

from .menu import menu_item_available_at_outlet
from .pricing import line_tax, line_total, recalculate_order_totals


def resolve_table(tenant_id, outlet_id, table_id) -> Table | None:
    if table_id is None:
        return None
    t = (
        Table.objects.filter(
            id=table_id,
            outlet_id=outlet_id,
            outlet__site__tenant_id=tenant_id,
            is_active=True,
        )
        .first()
    )
    if t is None:
        raise ValidationError({"table": "Invalid or inactive table for this outlet."})
    return t


def resolve_order_create(
    tenant: Tenant,
    membership: Membership,
    *,
    outlet_id,
    lines: list[dict],
) -> tuple[Outlet, list[dict]]:
    outlet = (
        Outlet.objects.filter(
            id=outlet_id,
            site__tenant_id=tenant.id,
            is_active=True,
        )
        .select_related("site")
        .first()
    )
    if outlet is None:
        raise ValidationError({"outlet": "Invalid or inactive outlet for this tenant."})
    if not outlet_belongs_to_membership(membership, outlet.id):
        raise ValidationError({"outlet": "You cannot create orders for this outlet."})

    resolved: list[dict] = []
    for row in lines:
        mid = row["menu_item"]
        qty = row["quantity"]
        mod_ids = row.get("modifier_option_ids") or []
        item = MenuItem.objects.filter(id=mid, tenant_id=tenant.id, is_active=True).first()
        if item is None:
            raise ValidationError({"lines": f"Unknown or inactive menu item: {mid}."})
        if not menu_item_available_at_outlet(item, outlet.id):
            raise ValidationError({"lines": f'"{item.name}" is not available at this outlet.'})
        resolved.append(
            {
                "menu_item": item,
                "quantity": qty,
                "modifier_option_ids": list(mod_ids),
            }
        )
    return outlet, resolved


def resolve_folio_for_order(
    tenant_id,
    membership: Membership,
    outlet: Outlet,
    folio_id,
) -> Folio | None:
    if not folio_id:
        return None
    folio = (
        Folio.objects.filter(
            id=folio_id,
            tenant_id=tenant_id,
            status=FolioStatus.OPEN,
        )
        .select_related("site")
        .first()
    )
    if folio is None:
        raise ValidationError({"folio": "Invalid folio or folio is not open."})
    if folio.site_id != outlet.site_id:
        raise ValidationError({"folio": "Folio must belong to the same site as the outlet."})
    if membership.sites.exists():
        allowed = set(membership.sites.values_list("pk", flat=True))
        if folio.site_id not in allowed:
            raise ValidationError({"folio": "You cannot use this folio."})
    return folio


@transaction.atomic
def set_open_order_folio(*, order: Order, membership: Membership, folio_id, user) -> Order:
    locked = Order.objects.select_for_update().select_related("outlet", "outlet__site").get(pk=order.pk)
    if locked.status != OrderStatus.OPEN or locked.is_paid:
        raise ValidationError("Folio can only be changed on open, unpaid orders.")
    folio = resolve_folio_for_order(
        locked.tenant_id,
        membership,
        locked.outlet,
        folio_id,
    )
    locked.folio = folio
    locked.save(update_fields=["folio", "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.folio_set",
        entity_type="order",
        entity_id=str(locked.id),
        payload={"folio_id": str(folio.id) if folio else None, "bill_reference": locked.bill_reference},
    )
    return locked


def default_currency_for_tenant(tenant: Tenant) -> str:
    try:
        return tenant.settings.default_currency
    except TenantSettings.DoesNotExist:
        return "USD"


def lookup_supermarket_item_for_code(
    *,
    tenant_id,
    outlet_id,
    code: str,
) -> tuple[MenuItem | None, str]:
    token = (code or "").strip()
    if not token:
        return None, ""
    outlet = Outlet.objects.filter(id=outlet_id, site__tenant_id=tenant_id, is_active=True).first()
    if outlet is None:
        return None, ""
    if outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
        return None, ""
    # Primary path: direct barcode.
    for item in MenuItem.objects.filter(tenant_id=tenant_id, is_active=True, barcode__iexact=token):
        if menu_item_available_at_outlet(item, outlet_id):
            return item, "barcode"
    # Fallback: supermarket PLU profile.
    profile = (
        SupermarketSkuProfile.objects.select_related("menu_item")
        .filter(
            tenant_id=tenant_id,
            is_active=True,
            plu_code__iexact=token,
            menu_item__is_active=True,
        )
        .first()
    )
    if profile and menu_item_available_at_outlet(profile.menu_item, outlet_id):
        return profile.menu_item, "plu"
    return None, ""


def normalize_supermarket_quantity(*, menu_item: MenuItem, quantity: Decimal) -> Decimal:
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    qty = quantity.quantize(Decimal("0.001"))
    profile = getattr(menu_item, "supermarket_profile", None)
    if profile is None:
        return qty
    if not profile.allow_fractional_quantity and profile.weighted_pricing_mode == WeightedPricingMode.UNIT:
        if qty != qty.quantize(Decimal("1")):
            raise ValidationError({"quantity": f"{menu_item.name} only allows whole units."})
    return qty


@transaction.atomic
def create_order_with_lines(
    *,
    tenant_id,
    outlet,
    created_by,
    currency: str,
    table_label: str,
    lines: list[dict],
    table: Table | None = None,
    folio=None,
) -> Order:
    order = Order.objects.create(
        tenant_id=tenant_id,
        outlet=outlet,
        table=table,
        created_by=created_by,
        currency=currency,
        table_label=table_label or "",
        folio=folio,
    )
    from apps.catalog.modifiers_service import resolve_modifier_selection_drfsafe

    for i, row in enumerate(lines):
        menu_item = row["menu_item"]
        quantity = row["quantity"]
        mod_ids = row.get("modifier_option_ids") or []
        per_unit_mod, mod_snapshot = resolve_modifier_selection_drfsafe(
            menu_item=menu_item,
            option_ids=mod_ids,
        )
        unit_price = menu_item.unit_price_for_outlet(outlet.id)
        eff_unit = unit_price + per_unit_mod
        sub = line_total(quantity, eff_unit)
        tax = line_tax(sub, menu_item.tax_rate_percent)
        OrderLine.objects.create(
            order=order,
            menu_item=menu_item,
            label=menu_item.name,
            quantity=quantity,
            unit_price=unit_price,
            line_total=sub,
            tax_amount=tax,
            pricing_source="menu",
            sort_order=i,
            kds_station=(menu_item.kds_station or "")[:32],
            modifiers_snapshot=mod_snapshot,
        )
    recalculate_order_totals(order)
    order.refresh_from_db()
    log_audit(
        tenant_id=tenant_id,
        user_id=created_by.id if created_by else None,
        action="order.created",
        entity_type="order",
        entity_id=str(order.id),
        payload={
            "bill_reference": order.bill_reference,
            "outlet_id": str(outlet.id),
            "table_id": str(table.id) if table else None,
            "total": str(order.total),
        },
    )
    return order


@transaction.atomic
def apply_promotion_to_order(*, order: Order, promotion: Promotion, user) -> Order:
    from django.utils import timezone as dj_tz

    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status != OrderStatus.OPEN or locked.is_paid:
        raise ValidationError("Promotion can only be applied to open, unpaid orders.")
    if promotion.tenant_id != locked.tenant_id or not promotion.is_active:
        raise ValidationError("Invalid promotion.")
    now = dj_tz.now()
    if promotion.starts_at > now or (promotion.ends_at and promotion.ends_at < now):
        raise ValidationError("Promotion is not valid at this time.")
    if promotion.outlets.exists() and not promotion.outlets.filter(pk=locked.outlet_id).exists():
        raise ValidationError("Promotion does not apply to this outlet.")
    if promotion.min_order_subtotal is not None and locked.subtotal < promotion.min_order_subtotal:
        raise ValidationError({"promotion": "Order subtotal is below the minimum for this promotion."})
    if promotion.discount_percent is not None:
        disc = (locked.subtotal * promotion.discount_percent / Decimal("100")).quantize(Decimal("0.01"))
    elif promotion.discount_amount is not None:
        disc = promotion.discount_amount
    else:
        raise ValidationError("Promotion is missing discount fields.")
    max_disc = locked.subtotal + locked.tax_total
    disc = min(disc, max_disc)
    locked.discount_amount = disc
    locked.applied_promotion = promotion
    locked.save(update_fields=["discount_amount", "applied_promotion", "updated_at"])
    recalculate_order_totals(locked)
    locked.refresh_from_db()
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.promotion_applied",
        entity_type="order",
        entity_id=str(locked.id),
        payload={"promotion_id": str(promotion.id), "discount_amount": str(disc)},
    )
    return locked


@transaction.atomic
def add_line_to_open_order(
    *,
    order: Order,
    menu_item: MenuItem,
    quantity: Decimal,
    user,
    modifier_option_ids: list | None = None,
) -> OrderLine:
    from apps.catalog.modifiers_service import resolve_modifier_selection_drfsafe

    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status != OrderStatus.OPEN:
        raise ValidationError("Lines can only be added to open orders.")
    if locked.is_paid:
        raise ValidationError("Cannot add lines to a paid order.")
    per_unit_mod, mod_snapshot = resolve_modifier_selection_drfsafe(
        menu_item=menu_item,
        option_ids=modifier_option_ids,
    )
    unit_price = menu_item.unit_price_for_outlet(locked.outlet_id)
    eff_unit = unit_price + per_unit_mod
    sub = line_total(quantity, eff_unit)
    tax = line_tax(sub, menu_item.tax_rate_percent)
    mx = locked.lines.aggregate(m=Max("sort_order"))["m"]
    next_sort = (mx if mx is not None else -1) + 1
    line = OrderLine.objects.create(
        order=locked,
        menu_item=menu_item,
        label=menu_item.name,
        quantity=quantity,
        unit_price=unit_price,
        line_total=sub,
        tax_amount=tax,
        pricing_source="menu",
        sort_order=next_sort,
        kds_station=(menu_item.kds_station or "")[:32],
        modifiers_snapshot=mod_snapshot,
    )
    recalculate_order_totals(locked)
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.line_added",
        entity_type="order",
        entity_id=str(locked.id),
        payload={"line_id": str(line.id), "menu_item_id": str(menu_item.id)},
    )
    return line


@transaction.atomic
def add_service_to_open_order(
    *,
    order: Order,
    service_offering: ServiceOffering,
    service_option: ServiceOfferingOption | None = None,
    quantity: Decimal,
    user,
) -> OrderLine:
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status != OrderStatus.OPEN:
        raise ValidationError("Services can only be added to open orders.")
    if locked.is_paid:
        raise ValidationError("Cannot add services to a paid order.")
    if service_offering.tenant_id != locked.tenant_id or not service_offering.is_active:
        raise ValidationError({"service_offering": "Unknown or inactive service for this workspace."})
    if not service_offering.available_at_outlet(locked.outlet_id):
        raise ValidationError({"service_offering": "Service is not available at this outlet."})
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    if service_option is not None:
        if service_option.service_offering_id != service_offering.id:
            raise ValidationError({"service_option": "Selected package does not belong to this service."})
        if not service_option.is_active:
            raise ValidationError({"service_option": "Selected package is inactive."})
        unit_price = service_option.price
        line_label = f"{service_offering.name} · {service_option.name}"
        kds_station = service_option.effective_station()
    else:
        unit_price = service_offering.default_price
        line_label = service_offering.name
        kds_station = (service_offering.kds_station or "service")[:32]
    sub = line_total(quantity, unit_price)
    tax = line_tax(sub, service_offering.tax_rate_percent)
    mx = locked.lines.aggregate(m=Max("sort_order"))["m"]
    next_sort = (mx if mx is not None else -1) + 1
    line = OrderLine.objects.create(
        order=locked,
        menu_item=None,
        label=line_label,
        quantity=quantity,
        unit_price=unit_price,
        line_total=sub,
        tax_amount=tax,
        pricing_source="service",
        sort_order=next_sort,
        kds_station=kds_station,
    )
    recalculate_order_totals(locked)
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.service_added",
        entity_type="order",
        entity_id=str(locked.id),
        payload={
            "line_id": str(line.id),
            "service_offering_id": str(service_offering.id),
            "service_option_id": str(service_option.id) if service_option else None,
        },
    )
    return line


@transaction.atomic
def add_supermarket_line_by_code(
    *,
    order: Order,
    code: str,
    quantity: Decimal,
    user,
) -> OrderLine:
    item, source = lookup_supermarket_item_for_code(
        tenant_id=order.tenant_id,
        outlet_id=order.outlet_id,
        code=code,
    )
    if item is None:
        raise ValidationError({"code": "No active SKU found for this barcode/PLU at this outlet."})
    qty = normalize_supermarket_quantity(menu_item=item, quantity=quantity)
    line = add_line_to_open_order(order=order, menu_item=item, quantity=qty, user=user)
    pricing_source = source
    profile = getattr(item, "supermarket_profile", None)
    if profile is not None and profile.weighted_pricing_mode == WeightedPricingMode.WEIGHTED:
        pricing_source = "weighted"
    line.pricing_source = pricing_source or "menu"
    line.save(update_fields=["pricing_source", "updated_at"])
    return line


@transaction.atomic
def apply_supermarket_line_discount(
    *,
    order: Order,
    line: OrderLine,
    user,
    discount_amount: Decimal | None = None,
    discount_percent: Decimal | None = None,
) -> OrderLine:
    locked_o = Order.objects.select_for_update().get(pk=order.pk)
    if locked_o.status != OrderStatus.OPEN or locked_o.is_paid:
        raise ValidationError("Discounts can only be changed on open, unpaid orders.")
    locked_ln = (
        OrderLine.objects.select_for_update()
        .select_related("menu_item")
        .get(pk=line.pk, order_id=locked_o.id)
    )
    if locked_ln.is_voided:
        raise ValidationError("Cannot discount a voided line.")
    if discount_amount is not None and discount_percent is not None:
        raise ValidationError({"discount": "Use either discount amount or discount percent."})
    gross = line_total(locked_ln.quantity, locked_ln.unit_price)
    if discount_percent is not None:
        if discount_percent < 0 or discount_percent > 100:
            raise ValidationError({"discount_percent": "Percent must be between 0 and 100."})
        discount = (gross * discount_percent / Decimal("100")).quantize(Decimal("0.01"))
    else:
        discount = (discount_amount or Decimal("0")).quantize(Decimal("0.01"))
        if discount < 0:
            raise ValidationError({"discount_amount": "Discount amount cannot be negative."})
    discount = min(discount, gross)
    net = (gross - discount).quantize(Decimal("0.01"))
    tax_rate = Decimal("0")
    if locked_ln.menu_item is not None and locked_ln.menu_item.tax_rate_percent is not None:
        tax_rate = locked_ln.menu_item.tax_rate_percent
    tax = line_tax(net, tax_rate)
    locked_ln.line_discount_amount = discount
    locked_ln.line_discount_percent = discount_percent
    locked_ln.line_total = net
    locked_ln.tax_amount = tax
    locked_ln.pricing_source = "manual"
    locked_ln.save(
        update_fields=[
            "line_discount_amount",
            "line_discount_percent",
            "line_total",
            "tax_amount",
            "pricing_source",
            "updated_at",
        ],
    )
    recalculate_order_totals(locked_o)
    log_audit(
        tenant_id=locked_o.tenant_id,
        user_id=user.id if user else None,
        action="order.line_discount_applied",
        entity_type="order_line",
        entity_id=str(locked_ln.id),
        payload={
            "order_id": str(locked_o.id),
            "line_discount_amount": str(discount),
            "line_discount_percent": str(discount_percent) if discount_percent is not None else None,
        },
    )
    return locked_ln


@transaction.atomic
def void_open_order_line(
    *,
    order: Order,
    line: OrderLine,
    reason: str,
    user,
) -> None:
    locked_o = Order.objects.select_for_update().get(pk=order.pk)
    if locked_o.status != OrderStatus.OPEN:
        raise ValidationError("Lines can only be voided on open orders.")
    if locked_o.is_paid:
        raise ValidationError("Cannot void lines on a paid order.")
    locked_ln = OrderLine.objects.select_for_update().get(pk=line.pk, order_id=locked_o.id)
    if locked_ln.is_voided:
        raise ValidationError("Line is already voided.")
    locked_ln.is_voided = True
    locked_ln.void_reason = (reason or "")[:255]
    locked_ln.voided_at = timezone.now()
    locked_ln.voided_by = user
    locked_ln.save(
        update_fields=["is_voided", "void_reason", "voided_at", "voided_by", "updated_at"]
    )
    recalculate_order_totals(locked_o)
    log_audit(
        tenant_id=locked_o.tenant_id,
        user_id=user.id if user else None,
        action="order.line_voided",
        entity_type="order_line",
        entity_id=str(locked_ln.id),
        payload={"order_id": str(locked_o.id), "reason": locked_ln.void_reason},
    )


@transaction.atomic
def adjust_open_order_line_quantity(
    *,
    order: Order,
    line: OrderLine,
    quantity: Decimal,
    user,
) -> OrderLine:
    locked_o = Order.objects.select_for_update().get(pk=order.pk)
    if locked_o.status != OrderStatus.OPEN:
        raise ValidationError("Line quantities can only be edited on open orders.")
    if locked_o.is_paid:
        raise ValidationError("Cannot edit lines on a paid order.")
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    locked_ln = (
        OrderLine.objects.select_for_update()
        .select_related("menu_item")
        .get(pk=line.pk, order_id=locked_o.id)
    )
    if locked_ln.is_voided:
        raise ValidationError("Cannot edit a voided line.")
    tax_rate = Decimal("0")
    if locked_ln.menu_item is not None and locked_ln.menu_item.tax_rate_percent is not None:
        tax_rate = locked_ln.menu_item.tax_rate_percent
    locked_ln.quantity = quantity
    locked_ln.line_total = line_total(quantity, locked_ln.unit_price)
    locked_ln.tax_amount = line_tax(locked_ln.line_total, tax_rate)
    locked_ln.save(update_fields=["quantity", "line_total", "tax_amount", "updated_at"])
    recalculate_order_totals(locked_o)
    log_audit(
        tenant_id=locked_o.tenant_id,
        user_id=user.id if user else None,
        action="order.line_quantity_updated",
        entity_type="order_line",
        entity_id=str(locked_ln.id),
        payload={"order_id": str(locked_o.id), "quantity": str(quantity)},
    )
    return locked_ln


@transaction.atomic
def hold_open_order(*, order: Order, hold_label: str, user) -> Order:
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status != OrderStatus.OPEN:
        raise ValidationError("Only open orders can be put on hold.")
    if locked.is_paid:
        raise ValidationError("Paid orders cannot be put on hold.")
    label = (hold_label or "").strip()[:64]
    if not label:
        raise ValidationError({"hold_label": "Hold label is required."})
    locked.table_label = label
    locked.save(update_fields=["table_label", "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.held",
        entity_type="order",
        entity_id=str(locked.id),
        payload={"hold_label": label},
    )
    return locked


@transaction.atomic
def cancel_open_unpaid_order(*, order: Order, user, reason: str = "") -> Order:
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status != OrderStatus.OPEN:
        raise ValidationError("Only open orders can be cancelled.")
    if locked.is_paid:
        raise ValidationError("Paid orders cannot be cancelled.")
    locked.status = OrderStatus.CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.cancelled",
        entity_type="order",
        entity_id=str(locked.id),
        payload={"reason": (reason or "")[:255]},
    )
    return locked


@transaction.atomic
def process_supermarket_line_return(
    *,
    order: Order,
    line: OrderLine,
    quantity: Decimal,
    reason: str,
    restock: bool,
    user,
) -> SupermarketLineReturn:
    locked_o = Order.objects.select_for_update().get(pk=order.pk)
    if locked_o.status != OrderStatus.CLOSED or not locked_o.is_paid:
        raise ValidationError("Returns can only be recorded against closed, paid orders.")
    locked_ln = (
        OrderLine.objects.select_for_update()
        .select_related("menu_item")
        .get(pk=line.pk, order_id=locked_o.id)
    )
    if locked_ln.is_voided:
        raise ValidationError("Cannot return a voided line.")
    if restock and Refund.objects.filter(order=locked_o, restocked=True).exists():
        raise ValidationError({"restock": "This order was already restocked by its final refund."})
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    returned = (
        SupermarketLineReturn.objects.filter(order_line=locked_ln).aggregate(s=Sum("quantity"))["s"]
        or Decimal("0")
    )
    remaining = locked_ln.quantity - returned
    if quantity > remaining:
        raise ValidationError({"quantity": f"Cannot exceed remaining returnable quantity {remaining}."})
    if restock:
        if not locked_ln.menu_item_id:
            raise ValidationError({"restock": "This line has no direct-sale stock to return."})
        sold = -(
            StockMovement.objects.filter(
                order=locked_o, menu_item_id=locked_ln.menu_item_id, reason=StockReason.SALE
            ).aggregate(s=Sum("quantity_change"))["s"] or Decimal("0")
        )
        restored = (
            SupermarketLineReturn.objects.filter(
                order=locked_o, order_line__menu_item_id=locked_ln.menu_item_id, restocked=True
            ).aggregate(s=Sum("quantity"))["s"] or Decimal("0")
        )
        if sold <= 0 or quantity > sold - restored:
            raise ValidationError({"restock": "Only stock consumed by this sale can be put back on hand."})
    ret = SupermarketLineReturn.objects.create(
        tenant_id=locked_o.tenant_id,
        order=locked_o,
        order_line=locked_ln,
        quantity=quantity,
        reason=(reason or "")[:255],
        restocked=restock,
        created_by=user,
    )
    if restock:
        apply_manual_stock_change(
            tenant_id=locked_o.tenant_id,
            outlet=locked_o.outlet,
            menu_item=locked_ln.menu_item,
            quantity_change=quantity,
            reason=StockReason.ADJUST_IN,
            user=user,
            note=f"Return {locked_o.bill_reference}"[:512],
        )
    log_audit(
        tenant_id=locked_o.tenant_id,
        user_id=user.id if user else None,
        action="order.line_returned",
        entity_type="order_line",
        entity_id=str(locked_ln.id),
        payload={
            "order_id": str(locked_o.id),
            "quantity": str(quantity),
            "restock": restock,
        },
    )
    return ret


@transaction.atomic
def open_pos_shift(*, tenant_id, outlet: Outlet, user, opening_cash: Decimal, note: str = "") -> PosShift:
    # Lock a row that exists even when there is no current shift. Otherwise two
    # concurrent opens can both observe an empty shift queryset.
    locked_outlet = Outlet.objects.select_for_update().filter(pk=outlet.pk, site__tenant_id=tenant_id).first()
    if locked_outlet is None:
        raise ValidationError({"outlet": "Choose an outlet in this workspace."})
    existing = PosShift.objects.select_for_update().filter(
        tenant_id=tenant_id,
        outlet=locked_outlet,
        status=PosShiftStatus.OPEN,
    ).first()
    if existing is not None:
        raise ValidationError("An open shift already exists for this outlet.")
    if opening_cash < 0:
        raise ValidationError({"opening_cash": "Opening cash cannot be negative."})
    shift = PosShift.objects.create(
        tenant_id=tenant_id,
        outlet=locked_outlet,
        opened_by=user,
        opening_cash=opening_cash,
        expected_cash=opening_cash,
        note=(note or "")[:255],
    )
    log_audit(
        tenant_id=tenant_id,
        user_id=user.id if user else None,
        action="pos.shift_opened",
        entity_type="pos_shift",
        entity_id=str(shift.id),
        payload={"outlet_id": str(locked_outlet.id), "opening_cash": str(opening_cash)},
    )
    return shift


def shift_cash_snapshot(*, shift: PosShift, until=None) -> dict[str, Decimal]:
    """Cash expected at a point in time, shared by the register and close command."""
    until = until or timezone.now()
    cash_payments = (
        Payment.objects.filter(
            tenant_id=shift.tenant_id,
            order__outlet_id=shift.outlet_id,
            method=PaymentMethod.CASH,
            created_at__gte=shift.opened_at,
            created_at__lte=until,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    ).quantize(Decimal("0.01"))
    cash_refunds = (
        Refund.objects.filter(
            tenant_id=shift.tenant_id,
            order__outlet_id=shift.outlet_id,
            payment__method=PaymentMethod.CASH,
            created_at__gte=shift.opened_at,
            created_at__lte=until,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    ).quantize(Decimal("0.01"))
    expected = (shift.opening_cash + cash_payments - cash_refunds).quantize(Decimal("0.01"))
    return {"cash_payments": cash_payments, "cash_refunds": cash_refunds, "expected": expected}


@transaction.atomic
def close_pos_shift(*, shift: PosShift, user, counted_cash: Decimal, note: str = "") -> PosShift:
    locked = PosShift.objects.select_for_update().get(pk=shift.pk)
    if locked.status != PosShiftStatus.OPEN:
        raise ValidationError("Only open shifts can be closed.")
    if counted_cash < 0:
        raise ValidationError({"counted_cash": "Counted cash cannot be negative."})
    closed_at = timezone.now()
    snapshot = shift_cash_snapshot(shift=locked, until=closed_at)
    expected = snapshot["expected"]
    locked.status = PosShiftStatus.CLOSED
    locked.closed_by = user
    locked.closed_at = closed_at
    locked.expected_cash = expected
    locked.counted_cash = counted_cash.quantize(Decimal("0.01"))
    locked.note = (note or locked.note or "")[:255]
    locked.save(
        update_fields=[
            "status",
            "closed_by",
            "closed_at",
            "expected_cash",
            "counted_cash",
            "note",
            "updated_at",
        ],
    )
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="pos.shift_closed",
        entity_type="pos_shift",
        entity_id=str(locked.id),
        payload={
            "expected_cash": str(expected),
            "counted_cash": str(locked.counted_cash),
            "cash_refunds": str(snapshot["cash_refunds"]),
        },
    )
    return locked
