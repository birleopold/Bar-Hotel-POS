from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max, Sum, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.accounts.models import Membership, MembershipRole
from apps.audit.services import log_audit
from apps.catalog.promotion_rules import promotion_matches_item
from apps.catalog.models import (
    MenuItem,
    ProductAlternateCode,
    ProductAlternateCode,
    ProductPackage,
    RetailProductGroup,
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
    CashDrawerMovement,
    Order,
    OrderLine,
    OrderStatus,
    OrderServiceMode,
    Payment,
    PaymentMethod,
    PosShift,
    PosShiftStatus,
    ShiftHandover,
    Workstation,
    Refund,
    SupermarketLineReturn,
    Table,
)
from apps.tenants.models import Outlet, OutletType, Tenant, TenantSettings

from .menu import menu_item_available_at_outlet
from .pricing import line_tax, line_total, recalculate_order_totals
from .price_books import qualifying_customer_price_rule


def require_active_retail_basket(order: Order) -> None:
    """Parked retail sales must be resumed before further POS writes.

    Hospitality table labels are real operational identifiers, not hold flags.
    """
    if (order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and order.status == OrderStatus.OPEN and order.table_label):
        raise ValidationError(
            "This basket is on hold. Resume it before changing items or collecting payment."
        )


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


HOSPITALITY_TABLE_OPERATOR_ROLES = frozenset({
    MembershipRole.OWNER,
    MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER,
    MembershipRole.OUTLET_MANAGER,
    MembershipRole.SERVER,
    MembershipRole.BARTENDER,
})
HOSPITALITY_TABLE_MANAGER_ROLES = frozenset({
    MembershipRole.OWNER,
    MembershipRole.TENANT_ADMIN,
    MembershipRole.SITE_MANAGER,
    MembershipRole.OUTLET_MANAGER,
})
HOSPITALITY_OUTLET_TYPES = frozenset({
    OutletType.RESTAURANT,
    OutletType.BAR,
    OutletType.LOUNGE,
    OutletType.CAFETERIA,
})


@transaction.atomic
def open_or_resume_table_order(
    *,
    tenant_id,
    outlet: Outlet,
    table_id,
    membership: Membership,
    user,
    guest_count: int | None = None,
) -> tuple[Order, bool]:
    """Open one hospitality check for a table, or resume its existing check.

    The table row is the concurrency boundary. A normal server/bartender may
    resume only their own live check; managers may investigate/resume any
    scoped table. Explicit table transfer remains a separate workflow.
    """
    if (
        membership is None
        or not membership.is_active
        or membership.tenant_id != tenant_id
        or membership.user_id != user.pk
        or membership.role not in HOSPITALITY_TABLE_OPERATOR_ROLES
    ):
        raise ValidationError({"table": "Your role cannot open table checks."})
    if (
        outlet.site.tenant_id != tenant_id
        or not outlet.is_active
        or outlet.outlet_type not in HOSPITALITY_OUTLET_TYPES
        or not outlet_belongs_to_membership(membership, outlet.pk)
    ):
        raise ValidationError({"table": "This table is not in an accessible hospitality section."})

    locked_table = (
        Table.objects.select_for_update()
        .select_related("outlet", "outlet__site")
        .filter(
            pk=table_id,
            outlet_id=outlet.pk,
            outlet__site__tenant_id=tenant_id,
            is_active=True,
        )
        .first()
    )
    if locked_table is None:
        raise ValidationError({"table": "Invalid or inactive table for this section."})

    live = list(
        Order.objects.select_for_update()
        .filter(
            tenant_id=tenant_id,
            outlet_id=outlet.pk,
            table=locked_table,
            status=OrderStatus.OPEN,
        )
        .select_related("created_by")
        .order_by("created_at")[:2]
    )
    if len(live) > 1:
        raise ValidationError({
            "table": "Multiple open checks are linked to this table. A manager must resolve them before service continues."
        })
    if live:
        order = live[0]
        if order.is_paid:
            raise ValidationError({
                "table": "This table has an open check already marked paid. Review that check before starting another."
            })
        if (
            membership.role not in HOSPITALITY_TABLE_MANAGER_ROLES
            and order.created_by_id != user.pk
        ):
            assigned = (
                order.created_by.get_full_name()
                or order.created_by.email
                if order.created_by else "another worker"
            )
            raise ValidationError({
                "table": f"This table is already assigned to {assigned}. Use the transfer workflow instead of taking it over."
            })
        return order, True

    if guest_count is None or guest_count < 1 or guest_count > 999:
        raise ValidationError({
            "guest_count": "Enter the number of guests (1–999) before opening the table."
        })
    order = create_order_with_lines(
        tenant_id=tenant_id,
        outlet=locked_table.outlet,
        created_by=user,
        currency=default_currency_for_tenant(locked_table.outlet.site.tenant),
        table_label=locked_table.label,
        table=locked_table,
        service_mode=OrderServiceMode.DINE_IN,
        guest_count=guest_count,
        lines=[],
    )
    return order, False


@transaction.atomic
def transfer_table_order(
    *,
    tenant_id,
    outlet: Outlet,
    order_id,
    target_table_id,
    membership: Membership,
    user,
) -> Order:
    """Move an open hospitality check to a vacant table in the same section."""
    if (
        membership is None
        or not membership.is_active
        or membership.tenant_id != tenant_id
        or membership.user_id != user.pk
        or membership.role not in HOSPITALITY_TABLE_OPERATOR_ROLES
    ):
        raise ValidationError({"table": "Your role cannot transfer table checks."})
    if (
        outlet.site.tenant_id != tenant_id
        or not outlet.is_active
        or outlet.outlet_type not in HOSPITALITY_OUTLET_TYPES
        or not outlet_belongs_to_membership(membership, outlet.pk)
    ):
        raise ValidationError({"table": "This check is not in an accessible hospitality section."})

    order = (
        Order.objects.select_for_update()
        .select_related("table", "created_by")
        .filter(
            pk=order_id,
            tenant_id=tenant_id,
            outlet_id=outlet.pk,
            status=OrderStatus.OPEN,
        )
        .first()
    )
    if order is None or order.table_id is None:
        raise ValidationError({"table": "Choose an open table check to transfer."})
    if order.is_paid:
        raise ValidationError({"table": "A paid check cannot be moved to another table."})
    if (
        membership.role not in HOSPITALITY_TABLE_MANAGER_ROLES
        and order.created_by_id != user.pk
    ):
        raise ValidationError({
            "table": "Only the assigned server or a manager can transfer this table."
        })

    source_id = order.table_id
    if str(source_id) == str(target_table_id):
        return order

    # Lock both table rows in deterministic UUID order to avoid opposite
    # transfers deadlocking each other.
    lock_ids = sorted([source_id, target_table_id], key=str)
    locked_tables = list(
        Table.objects.select_for_update()
        .select_related("outlet", "outlet__site")
        .filter(
            pk__in=lock_ids,
            outlet_id=outlet.pk,
            outlet__site__tenant_id=tenant_id,
            is_active=True,
        )
    )
    if len(locked_tables) != 2:
        raise ValidationError({"table": "Choose another active table in this section."})
    tables_by_id = {table.pk: table for table in locked_tables}
    source = tables_by_id.get(source_id)
    target = tables_by_id.get(target_table_id)
    if source is None or target is None:
        raise ValidationError({"table": "Source and destination must be in the same section."})

    occupied = (
        Order.objects.select_for_update()
        .filter(
            tenant_id=tenant_id,
            outlet_id=outlet.pk,
            table=target,
            status=OrderStatus.OPEN,
        )
        .exclude(pk=order.pk)
        .exists()
    )
    if occupied:
        raise ValidationError({
            "table": f"{target.label} already has an open check. Choose an available table."
        })

    order.table = target
    order.table_label = target.label
    order.save(update_fields=["table", "table_label", "updated_at"])
    log_audit(
        tenant_id=tenant_id,
        user_id=user.pk,
        action="order.table_transferred",
        entity_type="order",
        entity_id=str(order.pk),
        payload={
            "outlet_id": str(outlet.pk),
            "from_table_id": str(source.pk),
            "from_table_label": source.label,
            "to_table_id": str(target.pk),
            "to_table_label": target.label,
        },
    )
    return order


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
    if membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN) or membership.sites.exists():
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


def lookup_supermarket_sellable_for_code(
    *,
    tenant_id,
    outlet_id,
    code: str,
) -> tuple[MenuItem | None, str, ProductPackage | None]:
    token = (code or "").strip()
    if not token:
        return None, "", None
    outlet = Outlet.objects.filter(
        id=outlet_id, site__tenant_id=tenant_id, is_active=True,
    ).first()
    if outlet is None or outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
        return None, "", None

    # A base-product barcode keeps priority for backward compatibility.
    for item in MenuItem.objects.filter(
        tenant_id=tenant_id, is_active=True, barcode__iexact=token,
    ):
        if menu_item_available_at_outlet(item, outlet_id):
            return item, "barcode", None

    package = (
        ProductPackage.objects.select_related("menu_item")
        .filter(
            tenant_id=tenant_id,
            is_active=True,
            is_sellable=True,
            menu_item__is_active=True,
        )
        .filter(Q(barcode__iexact=token) | Q(sku_alias__iexact=token))
        .order_by("pk")
        .first()
    )
    if package and menu_item_available_at_outlet(package.menu_item, outlet_id):
        return package.menu_item, "package", package

    alternate = (
        ProductAlternateCode.objects.select_related("menu_item")
        .filter(
            tenant_id=tenant_id,
            is_active=True,
            code__iexact=token,
            menu_item__is_active=True,
        )
        .first()
    )
    if alternate and menu_item_available_at_outlet(alternate.menu_item, outlet_id):
        return alternate.menu_item, "alternate", None

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
        return profile.menu_item, "plu", None

    return None, "", None


def lookup_supermarket_item_for_code(
    *,
    tenant_id,
    outlet_id,
    code: str,
) -> tuple[MenuItem | None, str]:
    """Backward-compatible item lookup for callers that do not need package metadata."""
    item, source, _package = lookup_supermarket_sellable_for_code(
        tenant_id=tenant_id,
        outlet_id=outlet_id,
        code=code,
    )
    return item, source

def normalize_supermarket_quantity(*, menu_item: MenuItem, quantity: Decimal) -> Decimal:
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    qty = quantity.quantize(Decimal("0.001"))
    if qty != quantity:
        raise ValidationError({"quantity": "Quantity must have at most three decimal places."})
    profile = getattr(menu_item, "supermarket_profile", None)
    if profile is None:
        if qty != qty.quantize(Decimal("1")):
            raise ValidationError({"quantity": f"{menu_item.name} only allows whole units."})
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
    service_mode: str = "",
    guest_count: int | None = None,
) -> Order:
    if service_mode not in {"", *OrderServiceMode.values}:
        raise ValidationError({"service_mode": "Choose a supported order type."})
    if guest_count is not None and (guest_count < 1 or guest_count > 999):
        raise ValidationError({"guest_count": "Guest count must be between 1 and 999."})
    order = Order.objects.create(
        tenant_id=tenant_id,
        outlet=outlet,
        table=table,
        created_by=created_by,
        currency=currency,
        table_label=table_label or "",
        service_mode=service_mode,
        guest_count=guest_count,
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
            "service_mode": order.service_mode,
            "guest_count": order.guest_count,
            "total": str(order.total),
        },
    )
    return order


@transaction.atomic
def apply_promotion_to_order(*, order: Order, promotion: Promotion, user) -> Order:
    from django.utils import timezone as dj_tz

    locked = Order.objects.select_for_update().get(pk=order.pk)
    require_active_retail_basket(locked)
    if locked.status != OrderStatus.OPEN or locked.is_paid:
        raise ValidationError("Promotion can only be applied to open, unpaid orders.")
    if locked.payments.exists():
        raise ValidationError({"promotion": "Promotion cannot be changed after payment has started."})
    if locked.lines.filter(pricing_source="wholesale", is_voided=False).exists():
        raise ValidationError({"promotion": "Wholesale price tiers cannot be combined with order promotions."})
    if locked.lines.filter(price_book_rule__isnull=False, is_voided=False).exists():
        raise ValidationError({"promotion": "Customer price-book rates cannot be combined with order promotions yet."})
    if promotion.tenant_id != locked.tenant_id or not promotion.is_active:
        raise ValidationError("Invalid promotion.")
    now = dj_tz.now()
    if promotion.starts_at > now or (promotion.ends_at and promotion.ends_at < now):
        raise ValidationError("Promotion is not valid at this time.")
    if promotion.outlets.exists() and not promotion.outlets.filter(pk=locked.outlet_id).exists():
        raise ValidationError("Promotion does not apply to this outlet.")
    if promotion.min_order_subtotal is not None and locked.subtotal < promotion.min_order_subtotal:
        raise ValidationError({"promotion": "Order subtotal is below the minimum for this promotion."})
    if locked.lines.filter(is_voided=False).filter(
        Q(line_discount_amount__gt=0) | Q(line_discount_percent__isnull=False)
    ).exists():
        raise ValidationError({"promotion": "Order promotions cannot be stacked with manual line discounts."})

    target_is_scoped = bool(
        promotion.menu_item_id
        or promotion.product_family_id
        or promotion.category_id
        or (promotion.brand or "").strip()
    )
    discount_basis = locked.subtotal
    if target_is_scoped:
        active_lines = list(
            locked.lines.select_related("menu_item")
            .filter(is_voided=False, menu_item__isnull=False)
            .order_by("sort_order")
        )
        eligible_lines = [
            line
            for line in active_lines
            if promotion_matches_item(promotion, line.menu_item)
        ]
        if not eligible_lines:
            raise ValidationError({"promotion": "This promotion does not match any item in the basket."})
        discount_basis = sum(
            (line.line_total for line in eligible_lines),
            Decimal("0"),
        ).quantize(Decimal("0.01"))

    if promotion.discount_percent is not None:
        disc = (discount_basis * promotion.discount_percent / Decimal("100")).quantize(Decimal("0.01"))
    elif promotion.discount_amount is not None:
        disc = promotion.discount_amount
    else:
        raise ValidationError("Promotion is missing discount fields.")
    max_disc = discount_basis if target_is_scoped else locked.subtotal + locked.tax_total
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
        payload={
            "promotion_id": str(promotion.id),
            "promotion_target": promotion.target_label,
            "discount_basis": str(discount_basis),
            "discount_amount": str(disc),
        },
    )
    return locked


@transaction.atomic
def remove_promotion_from_order(*, order: Order, user) -> Order:
    """Remove an applied promotion from an open basket before payment starts."""

    locked = Order.objects.select_for_update().get(pk=order.pk)
    require_active_retail_basket(locked)
    if locked.status != OrderStatus.OPEN or locked.is_paid:
        raise ValidationError("Promotion can only be changed on an open unpaid order.")
    if locked.payments.exists():
        raise ValidationError({"promotion": "Promotion cannot be changed after payment has started."})
    if locked.applied_promotion_id is None and not locked.discount_amount:
        return locked

    before_promotion_id = locked.applied_promotion_id
    before_discount = locked.discount_amount
    locked.applied_promotion = None
    locked.discount_amount = Decimal("0.00")
    locked.save(update_fields=["applied_promotion", "discount_amount", "updated_at"])
    recalculate_order_totals(locked)
    locked.refresh_from_db()
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk if user else None,
        action="order.promotion_removed",
        entity_type="order",
        entity_id=str(locked.pk),
        payload={
            "promotion_id": str(before_promotion_id) if before_promotion_id else None,
            "discount_amount": str(before_discount),
        },
    )
    return locked


def _normalize_dine_in_seat(order: Order, seat_number) -> int | None:
    if seat_number in (None, ""):
        return None
    try:
        seat = int(seat_number)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"seat_number": "Choose a valid seat number."}) from exc
    if (
        order.outlet.outlet_type not in HOSPITALITY_OUTLET_TYPES
        or order.service_mode != OrderServiceMode.DINE_IN
    ):
        raise ValidationError({
            "seat_number": "Seats are available only on dine-in hospitality checks."
        })
    if not order.guest_count:
        raise ValidationError({
            "seat_number": "Record the guest count before assigning seats."
        })
    if seat < 1 or seat > order.guest_count:
        raise ValidationError({
            "seat_number": f"Choose a seat between 1 and {order.guest_count}."
        })
    return seat


@transaction.atomic
def assign_order_line_seat(
    *,
    order: Order,
    line: OrderLine,
    seat_number,
    user,
) -> tuple[OrderLine, bool]:
    locked = (
        Order.objects.select_for_update()
        .select_related("outlet")
        .get(pk=order.pk)
    )
    if locked.status != OrderStatus.OPEN or locked.is_paid:
        raise ValidationError({
            "seat_number": "Seats can be changed only before the check is settled."
        })
    seat = _normalize_dine_in_seat(locked, seat_number)
    locked_line = OrderLine.objects.select_for_update().filter(
        pk=line.pk,
        order=locked,
        is_voided=False,
    ).first()
    if locked_line is None:
        raise ValidationError({"line": "Choose an active item on this check."})
    if locked_line.seat_number == seat:
        return locked_line, False
    before = locked_line.seat_number
    locked_line.seat_number = seat
    locked_line.save(update_fields=["seat_number", "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk if user else None,
        action="order.line_seat_changed",
        entity_type="order_line",
        entity_id=str(locked_line.pk),
        payload={
            "order_id": str(locked.pk),
            "before": before,
            "after": seat,
        },
    )
    return locked_line, True


@transaction.atomic
def add_line_to_open_order(
    *,
    order: Order,
    menu_item: MenuItem,
    quantity: Decimal,
    user,
    modifier_option_ids: list | None = None,
    pricing_source: str = "menu",
    seat_number: int | None = None,
    unit_price_override: Decimal | None = None,
) -> OrderLine:
    from apps.catalog.modifiers_service import resolve_modifier_selection_drfsafe

    if pricing_source not in {"menu", "barcode", "plu", "weighted", "package", "serial", "alternate"}:
        raise ValidationError({"pricing_source": "Invalid retail scan source."})

    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status != OrderStatus.OPEN:
        raise ValidationError("Lines can only be added to open orders.")
    if locked.is_paid:
        raise ValidationError("Cannot add lines to a paid order.")
    require_active_retail_basket(locked)
    per_unit_mod, mod_snapshot = resolve_modifier_selection_drfsafe(
        menu_item=menu_item,
        option_ids=modifier_option_ids,
    )
    if locked.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}:
        quantity = normalize_supermarket_quantity(menu_item=menu_item, quantity=quantity)
    seat = _normalize_dine_in_seat(locked, seat_number)
    unit_price = menu_item.unit_price_for_outlet(locked.outlet_id)
    if unit_price_override is not None:
        override = Decimal(str(unit_price_override))
        if (
            not override.is_finite()
            or override < 0
            or override != override.quantize(Decimal("0.01"))
        ):
            raise ValidationError({"unit_price": "Retail unit price must use two decimal places."})
        unit_price = override
    base_unit_price = unit_price
    retail_checkout = locked.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
    price_book_allowed = bool(
        retail_checkout
        and unit_price_override is None
        and locked.customer_id
        and not locked.applied_promotion_id
        and not locked.discount_amount
        and not locked.payments.exists()
    )
    new_line_rule = (
        qualifying_customer_price_rule(
            tenant_id=locked.tenant_id,
            outlet_id=locked.outlet_id,
            customer_id=locked.customer_id,
            menu_item_id=menu_item.pk,
            quantity=quantity,
        )
        if price_book_allowed
        else None
    )
    if new_line_rule is not None:
        unit_price = new_line_rule.unit_price
    eff_unit = unit_price + per_unit_mod
    sub = line_total(quantity, eff_unit)
    tax = line_tax(sub, menu_item.tax_rate_percent)
    # Retail baskets group identical products on one row. The order row lock
    # serializes concurrent scans. Customer price books may change the effective
    # price when a quantity tier is crossed, but only before any payment exists.
    if retail_checkout:
        existing = (
            locked.lines.select_for_update(of=("self",)).filter(
                menu_item_id=menu_item.pk,
                is_voided=False,
                pricing_source__in=("menu", "barcode", "plu", "package", "serial", "alternate"),
                label=menu_item.name,
                line_discount_amount=Decimal("0"),
            ).order_by("sort_order")
        )
        for candidate in existing:
            if candidate.line_discount_percent is not None:
                continue
            if (candidate.modifiers_snapshot or []) != (mod_snapshot or []):
                continue
            if candidate.kds_status not in ("pending", ""):
                continue
            candidate_base = (
                candidate.price_book_base_unit_price
                if candidate.price_book_rule_id and candidate.price_book_base_unit_price is not None
                else candidate.unit_price
            )
            if candidate_base != base_unit_price:
                continue
            new_qty = candidate.quantity + quantity
            merged_rule = (
                qualifying_customer_price_rule(
                    tenant_id=locked.tenant_id,
                    outlet_id=locked.outlet_id,
                    customer_id=locked.customer_id,
                    menu_item_id=menu_item.pk,
                    quantity=new_qty,
                )
                if price_book_allowed
                else None
            )
            merged_price = merged_rule.unit_price if merged_rule is not None else candidate_base
            candidate.quantity = new_qty
            candidate.unit_price = merged_price
            candidate.price_book_rule = merged_rule
            candidate.price_book_base_unit_price = candidate_base if merged_rule is not None else None
            merged_eff_unit = merged_price + per_unit_mod
            candidate.line_total = line_total(new_qty, merged_eff_unit)
            candidate.tax_amount = line_tax(candidate.line_total, menu_item.tax_rate_percent)
            candidate.save(update_fields=[
                "quantity", "unit_price", "price_book_rule",
                "price_book_base_unit_price", "line_total", "tax_amount", "updated_at",
            ])
            recalculate_order_totals(locked)
            log_audit(
                tenant_id=locked.tenant_id,
                user_id=user.id if user else None,
                action="order.line_quantity_merged",
                entity_type="order_line",
                entity_id=str(candidate.id),
                payload={
                    "order_id": str(locked.id),
                    "added_quantity": str(quantity),
                    "new_quantity": str(new_qty),
                    "menu_item_id": str(menu_item.pk),
                    "price_book_rule_id": str(merged_rule.pk) if merged_rule else None,
                },
            )
            return candidate
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
        pricing_source=pricing_source,
        price_book_rule=new_line_rule,
        price_book_base_unit_price=base_unit_price if new_line_rule is not None else None,
        sort_order=next_sort,
        seat_number=seat,
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
        payload={
            "line_id": str(line.id),
            "menu_item_id": str(menu_item.id),
            "seat_number": seat,
            "price_book_rule_id": str(new_line_rule.pk) if new_line_rule else None,
        },
    )
    return line


@transaction.atomic
def add_retail_group_to_open_order(
    *,
    order: Order,
    retail_group: RetailProductGroup,
    quantity: Decimal,
    user,
) -> list[OrderLine]:
    """Expand a non-stock retail group into ordinary basket lines atomically."""

    locked = (
        Order.objects.select_for_update()
        .select_related("outlet")
        .get(pk=order.pk)
    )
    if locked.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
        raise ValidationError({"group": "Retail product groups are available only at retail checkout."})
    if locked.status != OrderStatus.OPEN or locked.is_paid:
        raise ValidationError({"group": "Groups can be added only to an open unpaid basket."})
    require_active_retail_basket(locked)
    if retail_group.tenant_id != locked.tenant_id or not retail_group.is_active:
        raise ValidationError({"group": "Choose an active retail group for this business."})
    try:
        group_qty = Decimal(str(quantity))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError({"quantity": "Enter a valid whole group quantity."}) from exc
    if (
        not group_qty.is_finite()
        or group_qty <= 0
        or group_qty != group_qty.to_integral_value()
        or group_qty > Decimal("999999")
    ):
        raise ValidationError({"quantity": "Group quantity must be a positive whole number."})

    if retail_group.lines.exclude(tenant_id=locked.tenant_id).exists():
        raise ValidationError({"group": "Retail group component scope is inconsistent. Ask an administrator to review it."})
    lines = list(
        retail_group.lines.filter(tenant_id=locked.tenant_id)
        .select_related("menu_item")
        .order_by("sort_order", "menu_item__name")
    )
    if not lines:
        raise ValidationError({"group": "This retail group has no products."})

    for component in lines:
        item = component.menu_item
        if item.tenant_id != locked.tenant_id or not item.is_active:
            raise ValidationError({"group": f'Product "{item.name}" is inactive or outside this business.'})
        if not menu_item_available_at_outlet(item, locked.outlet_id):
            raise ValidationError({"group": f'Product "{item.name}" is not available at this checkout section.'})
        expanded = (component.quantity * group_qty).quantize(Decimal("0.001"))
        if expanded <= 0 or expanded > Decimal("99999999999.999"):
            raise ValidationError({"group": f'Expanded quantity for "{item.name}" is outside checkout limits.'})
        if item.serial_tracking and expanded != expanded.to_integral_value():
            raise ValidationError({"group": f'Serialized product "{item.name}" must expand to whole units.'})

    added: list[OrderLine] = []
    for component in lines:
        expanded = (component.quantity * group_qty).quantize(Decimal("0.001"))
        added.append(
            add_line_to_open_order(
                order=locked,
                menu_item=component.menu_item,
                quantity=expanded,
                user=user,
                pricing_source="menu",
            )
        )

    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.pk if user else None,
        action="order.retail_group_added",
        entity_type="order",
        entity_id=str(locked.pk),
        payload={
            "retail_group_id": str(retail_group.pk),
            "retail_group_name": retail_group.name,
            "group_quantity": str(group_qty),
            "components": [
                {
                    "menu_item_id": str(component.menu_item_id),
                    "quantity_per_group": str(component.quantity),
                }
                for component in lines
            ],
        },
    )
    return added


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
    require_active_retail_basket(locked)
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
) -> OrderLine | list[OrderLine]:
    from apps.catalog.scale_labels import decode_scale_weight_label
    from apps.inventory.models import InventorySerialUnit, SerializedUnitStatus

    token = (code or "").strip()
    serial_unit = (
        InventorySerialUnit.objects.select_for_update()
        .select_related("menu_item")
        .filter(
            tenant_id=order.tenant_id,
            outlet_id=order.outlet_id,
            serial_number__iexact=token,
            status__in=[SerializedUnitStatus.AVAILABLE, SerializedUnitStatus.RETURNED],
            menu_item__is_active=True,
            menu_item__serial_tracking=True,
        )
        .first()
    )
    decoded = None if serial_unit is not None else decode_scale_weight_label(
        tenant_id=order.tenant_id, outlet_id=order.outlet_id, code=token,
    )
    package = None
    if serial_unit is not None:
        if Decimal(str(quantity)) != Decimal("1"):
            raise ValidationError({"quantity": "A serial / IMEI scan identifies one physical unit. Leave quantity at 1."})
        item = serial_unit.menu_item
        source = "serial"
        qty = Decimal("1")
    elif decoded is not None:
        if Decimal(str(quantity)) != Decimal("1"):
            raise ValidationError({"quantity": "Scale labels contain their weight. Leave scan quantity at 1."})
        item, qty = decoded
        source = "weighted"
    else:
        item, source, package = lookup_supermarket_sellable_for_code(
            tenant_id=order.tenant_id, outlet_id=order.outlet_id, code=code,
        )
        if item is None:
            retail_group = RetailProductGroup.objects.filter(
                tenant_id=order.tenant_id,
                is_active=True,
                code__iexact=token,
            ).first()
            if retail_group is not None:
                return add_retail_group_to_open_order(
                    order=order,
                    retail_group=retail_group,
                    quantity=quantity,
                    user=user,
                )
            raise ValidationError({"code": "No active SKU, barcode, PLU, package or retail group found at this outlet."})
        if package is not None:
            try:
                package_count = Decimal(str(quantity))
            except Exception as exc:
                raise ValidationError({"quantity": "Enter a valid whole package quantity."}) from exc
            if (
                not package_count.is_finite()
                or package_count <= 0
                or package_count != package_count.to_integral_value()
            ):
                raise ValidationError({"quantity": "Package scans use whole package quantities."})
            qty = (package_count * package.units_per_package).quantize(Decimal("0.001"))
        else:
            qty = quantity
    qty = normalize_supermarket_quantity(menu_item=item, quantity=qty)
    profile = getattr(item, "supermarket_profile", None)
    pricing_source = (
        "package"
        if source == "package"
        else "weighted"
        if profile is not None and profile.weighted_pricing_mode == WeightedPricingMode.WEIGHTED
        else source or "menu"
    )
    unit_price_override = None
    if source == "package" and package is not None and package.sell_price is not None:
        raw_unit_price = package.sell_price / package.units_per_package
        represented = raw_unit_price.quantize(Decimal("0.01"))
        if represented != raw_unit_price:
            raise ValidationError({
                "code": (
                    f'{package.name} has a package price that cannot be represented exactly '
                    "by the current two-decimal line price. Leave its package price blank for "
                    "base-unit pricing until advanced pack pricing is enabled."
                )
            })
        unit_price_override = represented
    # Source assignment and line creation/merge share the same order lock and
    # transaction. Stock quantity is always expressed in the product's base unit.
    line = add_line_to_open_order(
        order=order, menu_item=item, quantity=qty, user=user,
        pricing_source=pricing_source,
        unit_price_override=unit_price_override,
    )
    if source == "serial" and serial_unit is not None:
        from apps.inventory.services_serials import assign_serial_to_order_line
        assign_serial_to_order_line(
            order_line=line,
            serial_number=serial_unit.serial_number,
            user=user,
        )
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
    require_active_retail_basket(locked_o)
    if locked_o.status != OrderStatus.OPEN or locked_o.is_paid:
        raise ValidationError("Discounts can only be changed on open, unpaid orders.")
    locked_ln = (
        # menu_item is nullable for service rows: PostgreSQL cannot FOR UPDATE
        # the nullable side of its LEFT JOIN. Lock only the discountable line.
        OrderLine.objects.select_for_update(of=("self",))
        .get(pk=line.pk, order_id=locked_o.id)
    )
    if locked_ln.is_voided:
        raise ValidationError("Cannot discount a voided line.")
    if locked_ln.pricing_source == "wholesale":
        raise ValidationError({"discount": "Wholesale price tiers cannot be stacked with manual discounts."})
    if locked_ln.price_book_rule_id:
        raise ValidationError({"discount": "Customer price-book rates cannot be stacked with manual discounts yet."})
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
    require_active_retail_basket(locked_o)
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
    net_paid = (
        (Payment.objects.filter(order_id=locked_o.id).aggregate(s=Sum("amount"))["s"] or Decimal("0"))
        - (Refund.objects.filter(order_id=locked_o.id).aggregate(s=Sum("amount"))["s"] or Decimal("0"))
    )
    if locked_o.total < net_paid:
        excess = (net_paid - locked_o.total).quantize(Decimal("0.01"))
        raise ValidationError({
            "line": (
                f"Refund {locked_o.currency} {excess:.2f} before removing this item. "
                "The basket cannot fall below the net amount already received."
            )
        }, code="refund_required")
    from apps.inventory.services_serials import release_open_order_serial_reservations
    release_open_order_serial_reservations(order=locked_o, order_line=locked_ln, user=user)
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
    require_active_retail_basket(locked_o)
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    locked_ln = (
        # PostgreSQL cannot FOR UPDATE the nullable menu_item outer join.
        # Lock the line only; access its optional product details separately.
        OrderLine.objects.select_for_update(of=("self",))
        .get(pk=line.pk, order_id=locked_o.id)
    )
    if locked_ln.is_voided:
        raise ValidationError("Cannot edit a voided line.")
    if locked_o.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL} and locked_ln.menu_item_id:
        quantity = normalize_supermarket_quantity(menu_item=locked_ln.menu_item, quantity=quantity)
    if locked_ln.menu_item_id and locked_ln.menu_item.serial_tracking:
        from apps.inventory.models import InventorySerialUnit, SerializedUnitStatus
        reserved_count = InventorySerialUnit.objects.filter(
            tenant_id=locked_o.tenant_id,
            reserved_order_line=locked_ln,
            status=SerializedUnitStatus.RESERVED,
        ).count()
        if quantity != quantity.to_integral_value():
            raise ValidationError({"quantity": "Serialized products must use whole-unit quantities."})
        if int(quantity) < reserved_count:
            raise ValidationError({
                "quantity": (
                    f"Release {reserved_count - int(quantity)} assigned serial / IMEI "
                    "before reducing this serialized line."
                )
            })
    tax_rate = Decimal("0")
    if locked_ln.menu_item is not None and locked_ln.menu_item.tax_rate_percent is not None:
        tax_rate = locked_ln.menu_item.tax_rate_percent
    if locked_ln.pricing_source == "wholesale":
        if locked_o.payments.exists():
            raise ValidationError({"quantity": "Cannot change the quantity of a wholesale line after a payment; refund or review the sale."})
        from .wholesale import qualifying_rule
        tier = qualifying_rule(tenant_id=locked_o.tenant_id, outlet_id=locked_o.outlet_id,
                               menu_item_id=locked_ln.menu_item_id, quantity=quantity)
        if tier is None:
            base_price = locked_ln.menu_item.unit_price_for_outlet(locked_o.outlet_id)
            customer_rule = (
                qualifying_customer_price_rule(
                    tenant_id=locked_o.tenant_id,
                    outlet_id=locked_o.outlet_id,
                    customer_id=locked_o.customer_id,
                    menu_item_id=locked_ln.menu_item_id,
                    quantity=quantity,
                )
                if locked_o.customer_id
                and not locked_o.applied_promotion_id
                and not locked_o.discount_amount
                else None
            )
            locked_ln.unit_price = customer_rule.unit_price if customer_rule else base_price
            locked_ln.pricing_source = "menu"
            locked_ln.price_book_rule = customer_rule
            locked_ln.price_book_base_unit_price = base_price if customer_rule else None
        else:
            locked_ln.unit_price = tier.unit_price
            locked_ln.price_book_rule = None
            locked_ln.price_book_base_unit_price = None
        locked_ln.line_discount_amount = Decimal("0")
        locked_ln.line_discount_percent = None
    elif (
        locked_ln.menu_item_id
        and locked_ln.pricing_source in {"menu", "barcode", "plu", "weighted", "package", "serial", "alternate"}
        and locked_ln.line_discount_amount == Decimal("0")
        and locked_ln.line_discount_percent is None
    ):
        base_price = (
            locked_ln.price_book_base_unit_price
            if locked_ln.price_book_rule_id and locked_ln.price_book_base_unit_price is not None
            else locked_ln.menu_item.unit_price_for_outlet(locked_o.outlet_id)
        )
        can_reprice = bool(
            locked_o.customer_id
            and not locked_o.payments.exists()
            and not locked_o.applied_promotion_id
            and not locked_o.discount_amount
        )
        rule = (
            qualifying_customer_price_rule(
                tenant_id=locked_o.tenant_id,
                outlet_id=locked_o.outlet_id,
                customer_id=locked_o.customer_id,
                menu_item_id=locked_ln.menu_item_id,
                quantity=quantity,
            )
            if can_reprice
            else None
        )
        locked_ln.unit_price = rule.unit_price if rule else base_price
        locked_ln.price_book_rule = rule
        locked_ln.price_book_base_unit_price = base_price if rule else None
    locked_ln.quantity = quantity
    modifier_delta = Decimal("0")
    for snapshot in locked_ln.modifiers_snapshot or []:
        try:
            modifier_delta += Decimal(str(snapshot.get("price_delta") or "0"))
        except (InvalidOperation, TypeError, ValueError, AttributeError):
            continue
    locked_ln.line_total = line_total(quantity, locked_ln.unit_price + modifier_delta)
    locked_ln.tax_amount = line_tax(locked_ln.line_total, tax_rate)
    locked_ln.save(update_fields=[
        "quantity", "unit_price", "pricing_source", "price_book_rule",
        "price_book_base_unit_price", "line_discount_amount", "line_discount_percent",
        "line_total", "tax_amount", "updated_at",
    ])
    recalculate_order_totals(locked_o)
    # Open orders may already have partial tenders. A quantity reduction
    # cannot reduce the sale below money already received. The atomic
    # transaction rolls back both the edited line and recalculated total.
    paid_so_far = (
        (Payment.objects.filter(order_id=locked_o.id).aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00"))
        - (Refund.objects.filter(order_id=locked_o.id).aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00"))
    )
    if locked_o.total < paid_so_far:
        excess = (paid_so_far - locked_o.total).quantize(Decimal("0.01"))
        raise ValidationError({
            "quantity": (
                f"Refund {locked_o.currency} {excess:.2f} before applying this reduction. "
                f"The basket would otherwise be below the net amount already received "
                f"({locked_o.currency} {paid_so_far:.2f})."
            )
        }, code="refund_required")
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
def resume_held_retail_order(*, order: Order, user) -> Order:
    """Return a parked retail basket to the active register without settling it.

    The original order, tenders, pricing and audit history remain unchanged.
    Hospitality table labels are deliberately not managed by this workflow.
    """
    locked = Order.objects.select_for_update().select_related("outlet").get(
        pk=order.pk, tenant_id=order.tenant_id, outlet_id=order.outlet_id,
    )
    if locked.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
        raise ValidationError("Only supermarket or retail baskets can be resumed here.")
    if locked.status != OrderStatus.OPEN or locked.is_paid:
        raise ValidationError("Only open, not fully paid baskets can be resumed.")
    if not locked.table_label:
        return locked
    previous_label = locked.table_label
    locked.table_label = ""
    locked.save(update_fields=["table_label", "updated_at"])
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.resumed",
        entity_type="order",
        entity_id=str(locked.pk),
        payload={"previous_hold_label": previous_label},
    )
    return locked


@transaction.atomic
def cancel_open_unpaid_order(*, order: Order, user, reason: str = "") -> Order:
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status != OrderStatus.OPEN:
        raise ValidationError("Only open orders can be cancelled.")
    if locked.is_paid:
        raise ValidationError("Paid orders cannot be cancelled.")
    # A part-paid basket is still OPEN/is_paid=False. Never abandon money
    # already taken without a separately audited refund/reconciliation.
    recorded = (
        Payment.objects.filter(order_id=locked.id, tenant_id=locked.tenant_id)
        .aggregate(s=Sum("amount"))["s"] or Decimal("0")
    )
    refunded = (
        Refund.objects.filter(order_id=locked.id, tenant_id=locked.tenant_id)
        .aggregate(s=Sum("amount"))["s"] or Decimal("0")
    )
    if recorded > refunded:
        remaining_refund = (recorded - refunded).quantize(Decimal("0.01"))
        raise ValidationError(
            (
                f"Refund {locked.currency} {remaining_refund:.2f} with supervisor approval "
                "before cancelling this basket."
            ),
            code="refund_required",
        )
    locked.status = OrderStatus.CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    from apps.inventory.services_serials import release_open_order_serial_reservations
    release_open_order_serial_reservations(order=locked, user=user)
    log_audit(
        tenant_id=locked.tenant_id,
        user_id=user.id if user else None,
        action="order.cancelled",
        entity_type="order",
        entity_id=str(locked.id),
        payload={
            "reason": (reason or "")[:255],
            "recorded_payments": str(recorded),
            "recorded_refunds": str(refunded),
            "net_payment": str((recorded - refunded).quantize(Decimal("0.01"))),
        },
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
    idempotency_key: str = "",
    serial_numbers=None,
) -> SupermarketLineReturn:
    locked_o = Order.objects.select_for_update().get(pk=order.pk)
    if locked_o.status != OrderStatus.CLOSED or not locked_o.is_paid:
        raise ValidationError("Returns can only be recorded against closed, paid orders.")
    locked_ln = (
        # The optional product is nullable; locking its outer join raises
        # NotSupportedError on PostgreSQL. Lock only this returnable line.
        OrderLine.objects.select_for_update(of=("self",))
        .get(pk=line.pk, order_id=locked_o.id)
    )
    if locked_ln.is_voided:
        raise ValidationError("Cannot return a voided line.")
    if restock and Refund.objects.filter(order=locked_o, restocked=True).exists():
        raise ValidationError({"restock": "This order was already restocked by its final refund."})
    if quantity <= Decimal("0"):
        raise ValidationError({"quantity": "Quantity must be greater than zero."})

    request_key = str(idempotency_key or "").strip()
    if request_key:
        existing = SupermarketLineReturn.objects.select_for_update().filter(
            tenant_id=locked_o.tenant_id,
            idempotency_key=request_key,
        ).first()
        if existing is not None:
            if (
                existing.order_id != locked_o.id
                or existing.order_line_id != locked_ln.id
                or existing.quantity != quantity
                or existing.restocked != restock
                or existing.reason != (reason or "")[:255]
            ):
                raise ValidationError({
                    "Idempotency-Key": "This physical return key was already used for different details."
                })
            if locked_ln.menu_item_id and locked_ln.menu_item.serial_tracking:
                from apps.inventory.services_serials import normalize_serial_numbers
                supplied = {value.casefold() for value in normalize_serial_numbers(serial_numbers)}
                linked = {
                    value.casefold()
                    for value in existing.serialized_unit_links.values_list(
                        "serial_unit__serial_number", flat=True
                    )
                }
                if supplied != linked:
                    raise ValidationError({
                        "Idempotency-Key": "This return key was already used with different serial / IMEI values."
                    })
            existing.idempotent_replay = True
            return existing

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
    serial_units = []
    if locked_ln.menu_item_id:
        from apps.inventory.services_serials import lock_serial_units_for_return
        serial_units = lock_serial_units_for_return(
            order=locked_o,
            order_line=locked_ln,
            quantity=quantity,
            serial_numbers=serial_numbers,
        )
    try:
        with transaction.atomic():
            ret = SupermarketLineReturn.objects.create(
                tenant_id=locked_o.tenant_id,
                order=locked_o,
                order_line=locked_ln,
                quantity=quantity,
                reason=(reason or "")[:255],
                restocked=restock,
                created_by=user,
                idempotency_key=request_key,
            )
    except IntegrityError:
        if not request_key:
            raise
        ret = SupermarketLineReturn.objects.select_for_update().get(
            tenant_id=locked_o.tenant_id,
            idempotency_key=request_key,
        )
        if (
            ret.order_id != locked_o.id
            or ret.order_line_id != locked_ln.id
            or ret.quantity != quantity
            or ret.restocked != restock
            or ret.reason != (reason or "")[:255]
        ):
            raise ValidationError({
                "Idempotency-Key": "This physical return key was already used for different details."
            })
        ret.idempotent_replay = True
        return ret

    if serial_units:
        from apps.inventory.services_serials import complete_serialized_return
        complete_serialized_return(
            return_record=ret,
            units=serial_units,
            restock=restock,
            user=user,
        )
    elif restock:
        if not locked_ln.menu_item_id:
            raise ValidationError({"restock": "This line has no direct-sale stock to return."})
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
            "idempotency_key": request_key,
        },
    )
    ret.idempotent_replay = False
    return ret


@transaction.atomic
def open_pos_shift(*, tenant_id, outlet: Outlet, user, opening_cash: Decimal, note: str = "", workstation=None, handover_id=None) -> PosShift:
    # Lock a row that exists even when there is no current shift. Otherwise two
    # concurrent opens can both observe an empty shift queryset.
    locked_outlet = Outlet.objects.select_for_update().filter(pk=outlet.pk, site__tenant_id=tenant_id).first()
    if locked_outlet is None:
        raise ValidationError({"outlet": "Choose an outlet in this workspace."})
    if workstation is not None:
        workstation = Workstation.objects.select_for_update().filter(
            pk=workstation.pk, tenant_id=tenant_id, outlet=locked_outlet, is_active=True,
        ).first()
        if workstation is None:
            raise ValidationError({"workstation": "Choose an active workstation in this section."})
    pending = ShiftHandover.objects.filter(
        tenant_id=tenant_id, shift__outlet=locked_outlet, shift__workstation=workstation,
    ).exclude(status=ShiftHandover.Status.ACCEPTED)
    if handover_id is not None:
        pending = pending.exclude(pk=handover_id, status=ShiftHandover.Status.APPROVED)
    if pending.exists():
        raise ValidationError("Complete this register's handover before opening the next shift.")
    open_shifts = PosShift.objects.select_for_update().filter(
        tenant_id=tenant_id, outlet=locked_outlet, status=PosShiftStatus.OPEN,
    )
    if workstation is not None:
        open_shifts = open_shifts.filter(
            Q(workstation__isnull=True) | Q(cash_attribution=False) | Q(workstation=workstation)
        )
    if open_shifts.exists():
        raise ValidationError("This register already has an open shift, or a section-wide shift must be closed first.")
    if opening_cash < 0:
        raise ValidationError({"opening_cash": "Opening cash cannot be negative."})
    shift = PosShift.objects.create(
        tenant_id=tenant_id,
        outlet=locked_outlet,
        opened_by=user,
        workstation=workstation,
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
        payload={"outlet_id": str(locked_outlet.id), "opening_cash": str(opening_cash),
                 "workstation_id": str(workstation.id) if workstation else None},
    )
    return shift


def shift_cash_snapshot(*, shift: PosShift, until=None) -> dict[str, Decimal]:
    """Cash expected at a point in time, shared by the register and close command."""
    until = until or shift.closed_at or timezone.now()
    payments = Payment.objects.filter(tenant_id=shift.tenant_id, order__outlet_id=shift.outlet_id, method=PaymentMethod.CASH)
    refunds = Refund.objects.filter(tenant_id=shift.tenant_id, order__outlet_id=shift.outlet_id, payment__method=PaymentMethod.CASH)
    if shift.cash_attribution:
        payments = payments.filter(shift=shift)
        refunds = refunds.filter(shift=shift)
    else:
        # Historical/open legacy shifts retain their original time-window totals.
        payments = payments.filter(created_at__gte=shift.opened_at, created_at__lte=until)
        refunds = refunds.filter(created_at__gte=shift.opened_at, created_at__lte=until)
    cash_payments = (payments.aggregate(s=Sum("amount"))["s"] or Decimal("0")).quantize(Decimal("0.01"))
    cash_refunds = (refunds.aggregate(s=Sum("amount"))["s"] or Decimal("0")).quantize(Decimal("0.01"))
    movements = CashDrawerMovement.objects.filter(tenant_id=shift.tenant_id, shift=shift, created_at__lte=until)
    def total(direction):
        return (movements.filter(direction=direction).aggregate(s=Sum("amount"))["s"] or Decimal("0")).quantize(Decimal("0.01"))
    float_added, drops, payouts = total("float_add"), total("drop"), total("payout")
    expected = (shift.opening_cash + cash_payments - cash_refunds + float_added - drops - payouts).quantize(Decimal("0.01"))
    return {"cash_payments": cash_payments, "cash_refunds": cash_refunds, "float_added": float_added, "drops": drops, "payouts": payouts, "expected": expected}


@transaction.atomic
def close_pos_shift(*, shift: PosShift, user, counted_cash: Decimal, note: str = "") -> PosShift:
    Outlet.objects.select_for_update().get(pk=shift.outlet_id, site__tenant_id=shift.tenant_id)
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
            "outlet_id": str(locked.outlet_id),
            "workstation_id": str(locked.workstation_id) if locked.workstation_id else None,
            "cash_attribution": locked.cash_attribution,
            "opening_cash": str(locked.opening_cash),
            "cash_payments": str(snapshot["cash_payments"]),
            "cash_refunds": str(snapshot["cash_refunds"]),
            "float_added": str(snapshot["float_added"]),
            "drops": str(snapshot["drops"]),
            "payouts": str(snapshot["payouts"]),
            "expected_cash": str(expected),
            "counted_cash": str(locked.counted_cash),
            "variance": str(
                (locked.counted_cash - expected).quantize(Decimal("0.01"))
            ),
            "variance_explanation": locked.note,
        },
    )
    return locked
