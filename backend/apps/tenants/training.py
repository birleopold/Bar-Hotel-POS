"""Deterministic retail/supermarket sample pack for isolated training tenants."""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import MenuCategory, MenuItem
from apps.customers.models import Customer
from apps.finance.models import CashbookEntry, FinancePostingLink
from apps.inventory.models import StockBalance, StockMovement, StockReason
from apps.pos.models import Order, OrderLine, SupermarketLineReturn
from apps.pos.services.payments import record_order_payment, record_order_refund
from apps.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    Supplier,
)
from apps.tenants.business_lines import normalize_business_lines
from apps.tenants.models import Outlet, Tenant, TrainingWorkspaceState


TRAINING_CATEGORY = "Training products"
TRAINING_CUSTOMER_EMAIL = "training.customer@example.invalid"
TRAINING_SUPPLIER = "Training Wholesale Supplier"
TRAINING_PO_REFERENCE = "TRAINING-PO-001"

EXERCISES = {
    "cashier": [
        {
            "key": "cashier_scan",
            "title": "Scan or search a training product and add it to the basket.",
        },
        {
            "key": "cashier_hold",
            "title": "Hold one basket, serve another customer, then resume it.",
        },
        {
            "key": "cashier_split",
            "title": "Complete a training basket with two payment methods.",
        },
        {
            "key": "cashier_return",
            "title": "Review the sample return and practice a return/refund.",
        },
    ],
    "storekeeper": [
        {
            "key": "stock_review",
            "title": "Review training stock and identify the low-stock product.",
        },
        {
            "key": "po_receive",
            "title": "Open the training purchase order and receive stock.",
        },
        {
            "key": "stock_count",
            "title": "Create a stock count and reconcile a small variance.",
        },
    ],
    "manager": [
        {
            "key": "manager_sales",
            "title": "Review Sales Summary and find the training sale/refund.",
        },
        {
            "key": "manager_exception",
            "title": "Open Management → Exceptions and review one control signal.",
        },
        {
            "key": "manager_accounting",
            "title": "Preview the accounting export and inspect its validation state.",
        },
    ],
}


def assert_training_tenant(tenant: Tenant) -> None:
    if not tenant.is_training:
        raise ValidationError(
            {"training": "This operation is allowed only in an isolated training workspace."}
        )


def _retail_outlet(tenant: Tenant):
    try:
        lines = set(normalize_business_lines(tenant.settings.business_lines))
    except Exception:
        lines = set()
    if lines and not lines.intersection({"retail", "supermarket"}):
        raise ValidationError(
            {
                "training": (
                    "The current training pack is for Retail/Supermarket workspaces. "
                    "Hospitality training will use a separate sample pack."
                )
            }
        )
    outlet = (
        Outlet.objects.filter(
            site__tenant=tenant,
            is_active=True,
            outlet_type__in=["retail", "supermarket"],
        )
        .select_related("site")
        .order_by("created_at", "pk")
        .first()
    )
    if outlet is None:
        raise ValidationError(
            {"training": "Create an active Retail/Supermarket section before seeding training data."}
        )
    return outlet


def _delete_managed_sample_pack(*, tenant, state):
    ids = state.sample_ids or {}

    payment_ids = [str(value) for value in ids.get("payment_ids", [])]
    refund_ids = [str(value) for value in ids.get("refund_ids", [])]
    posting_links = list(
        FinancePostingLink.objects.filter(
            tenant=tenant,
            source_id__in=[*payment_ids, *refund_ids],
        ).values_list("pk", "cashbook_entry_id")
    )
    if posting_links:
        cashbook_ids = [row[1] for row in posting_links]
        FinancePostingLink.objects.filter(
            pk__in=[row[0] for row in posting_links]
        ).delete()
        CashbookEntry.objects.filter(
            tenant=tenant,
            pk__in=cashbook_ids,
        ).delete()

    return_ids = ids.get("return_ids", [])
    if return_ids:
        SupermarketLineReturn.objects.filter(
            tenant=tenant,
            pk__in=return_ids,
        ).delete()

    item_ids = ids.get("menu_item_ids", [])
    if item_ids:
        StockMovement.objects.filter(
            tenant=tenant,
            menu_item_id__in=item_ids,
        ).delete()
        StockBalance.objects.filter(
            tenant=tenant,
            menu_item_id__in=item_ids,
        ).delete()

    order_ids = ids.get("order_ids", [])
    if order_ids:
        Order.objects.filter(tenant=tenant, pk__in=order_ids).delete()

    po_ids = ids.get("purchase_order_ids", [])
    if po_ids:
        PurchaseOrder.objects.filter(tenant=tenant, pk__in=po_ids).delete()

    supplier_ids = ids.get("supplier_ids", [])
    if supplier_ids:
        Supplier.objects.filter(tenant=tenant, pk__in=supplier_ids).delete()

    customer_ids = ids.get("customer_ids", [])
    if customer_ids:
        Customer.objects.filter(tenant=tenant, pk__in=customer_ids).delete()

    if item_ids:
        MenuItem.objects.filter(tenant=tenant, pk__in=item_ids).delete()

    category_ids = ids.get("category_ids", [])
    if category_ids:
        MenuCategory.objects.filter(
            tenant=tenant,
            pk__in=category_ids,
        ).delete()


@transaction.atomic
def seed_retail_training_workspace(*, tenant: Tenant, user, reset=False):
    assert_training_tenant(tenant)
    outlet = _retail_outlet(tenant)
    state, _ = TrainingWorkspaceState.objects.select_for_update().get_or_create(
        tenant=tenant
    )
    if state.sample_ids and not reset:
        return state, True
    if reset:
        _delete_managed_sample_pack(tenant=tenant, state=state)

    category = MenuCategory.objects.create(
        tenant=tenant,
        name=TRAINING_CATEGORY,
        sort_order=900,
    )
    products = [
        MenuItem.objects.create(
            tenant=tenant,
            category=category,
            name="Training Bottled Water",
            sku="TRAIN-WATER",
            barcode="990000000001",
            unit_price=Decimal("2000.00"),
            tax_rate_percent=Decimal("0.00"),
            track_inventory=True,
            reorder_level=Decimal("5.000"),
        ),
        MenuItem.objects.create(
            tenant=tenant,
            category=category,
            name="Training Bar Soap",
            sku="TRAIN-SOAP",
            barcode="990000000002",
            unit_price=Decimal("4500.00"),
            tax_rate_percent=Decimal("0.00"),
            track_inventory=True,
            reorder_level=Decimal("8.000"),
        ),
        MenuItem.objects.create(
            tenant=tenant,
            category=category,
            name="Training Cooking Oil 1L",
            sku="TRAIN-OIL",
            barcode="990000000003",
            unit_price=Decimal("9000.00"),
            tax_rate_percent=Decimal("0.00"),
            track_inventory=True,
            reorder_level=Decimal("6.000"),
        ),
        MenuItem.objects.create(
            tenant=tenant,
            category=category,
            name="Training Rice 1kg",
            sku="TRAIN-RICE",
            barcode="990000000004",
            unit_price=Decimal("5000.00"),
            tax_rate_percent=Decimal("0.00"),
            track_inventory=True,
            reorder_level=Decimal("10.000"),
        ),
    ]
    stock_rows = [
        (products[0], Decimal("24.000"), Decimal("1200.0000")),
        (products[1], Decimal("4.000"), Decimal("2800.0000")),
        (products[2], Decimal("12.000"), Decimal("6200.0000")),
        (products[3], Decimal("30.000"), Decimal("3200.0000")),
    ]
    for item, quantity, cost in stock_rows:
        StockBalance.objects.create(
            tenant=tenant,
            outlet=outlet,
            menu_item=item,
            quantity=quantity,
            average_unit_cost=cost,
            cost_basis_complete=True,
        )
        StockMovement.objects.create(
            tenant=tenant,
            outlet=outlet,
            menu_item=item,
            quantity_change=quantity,
            reason=StockReason.ADJUST_IN,
            created_by=user,
            note=f"TRAINING baseline generation {state.generation + 1}",
        )

    customer = Customer.objects.create(
        tenant=tenant,
        name="Training Customer",
        email=TRAINING_CUSTOMER_EMAIL,
        phone="+256700000000",
        notes="Sample customer for training exercises only.",
        created_by=user,
    )
    supplier = Supplier.objects.create(
        tenant=tenant,
        name=TRAINING_SUPPLIER,
        email="training.supplier@example.invalid",
        phone="+256700000001",
        notes="Sample supplier for training exercises only.",
    )
    po = PurchaseOrder.objects.create(
        tenant=tenant,
        supplier=supplier,
        outlet=outlet,
        status=PurchaseOrderStatus.DRAFT,
        reference=TRAINING_PO_REFERENCE,
        notes="Training PO: receive this during the storekeeper exercise.",
        created_by=user,
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po,
        menu_item=products[1],
        quantity_ordered=Decimal("12.000"),
        unit_cost=Decimal("2750.00"),
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po,
        menu_item=products[2],
        quantity_ordered=Decimal("6.000"),
        unit_cost=Decimal("6000.00"),
    )

    order = Order.objects.create(
        tenant=tenant,
        customer=customer,
        outlet=outlet,
        subtotal=Decimal("6500.00"),
        tax_total=Decimal("0.00"),
        total=Decimal("6500.00"),
        currency=tenant.settings.default_currency,
        created_by=user,
    )
    water_line = OrderLine.objects.create(
        order=order,
        menu_item=products[0],
        label=products[0].name,
        quantity=Decimal("1.000"),
        unit_price=Decimal("2000.00"),
        line_total=Decimal("2000.00"),
        merchandise_category_snapshot=category.name,
        merchandise_sku_snapshot=products[0].sku,
        inventory_tracked_snapshot=True,
        sort_order=0,
    )
    OrderLine.objects.create(
        order=order,
        menu_item=products[1],
        label=products[1].name,
        quantity=Decimal("1.000"),
        unit_price=Decimal("4500.00"),
        line_total=Decimal("4500.00"),
        merchandise_category_snapshot=category.name,
        merchandise_sku_snapshot=products[1].sku,
        inventory_tracked_snapshot=True,
        sort_order=1,
    )
    payment, _ = record_order_payment(
        order=order,
        user=user,
        amount=Decimal("6500.00"),
        method="cash",
        idempotency_key=f"training:{tenant.pk}:generation:{state.generation + 1}:sale",
    )
    refund, _ = record_order_refund(
        order=order,
        user=user,
        amount=Decimal("2000.00"),
        reason="Training damaged-item return",
        idempotency_key=f"training:{tenant.pk}:generation:{state.generation + 1}:refund",
        restock=False,
        payment_id=payment.pk,
    )
    line_return = SupermarketLineReturn.objects.create(
        refund=refund,
        tenant=tenant,
        order=order,
        order_line=water_line,
        quantity=Decimal("1.000"),
        reason="Training damaged-item return",
        restocked=False,
        created_by=user,
        idempotency_key=f"training:{tenant.pk}:generation:{state.generation + 1}:return",
    )

    state.generation += 1
    state.seeded_at = timezone.now()
    state.seeded_by = user
    state.exercise_progress = {}
    state.sample_ids = {
        "category_ids": [str(category.pk)],
        "menu_item_ids": [str(item.pk) for item in products],
        "customer_ids": [str(customer.pk)],
        "supplier_ids": [str(supplier.pk)],
        "purchase_order_ids": [str(po.pk)],
        "order_ids": [str(order.pk)],
        "payment_ids": [str(payment.pk)],
        "refund_ids": [str(refund.pk)],
        "return_ids": [str(line_return.pk)],
        "outlet_id": str(outlet.pk),
    }
    state.save(
        update_fields=[
            "generation",
            "seeded_at",
            "seeded_by",
            "exercise_progress",
            "sample_ids",
            "updated_at",
        ]
    )
    return state, False


@transaction.atomic
def set_training_exercise_progress(*, tenant, user, exercise_key, completed):
    assert_training_tenant(tenant)
    valid = {
        item["key"]
        for group in EXERCISES.values()
        for item in group
    }
    if exercise_key not in valid:
        raise ValidationError({"exercise": "Unknown training exercise."})
    state = TrainingWorkspaceState.objects.select_for_update().get(tenant=tenant)
    progress = dict(state.exercise_progress or {})
    progress[exercise_key] = {
        "completed": bool(completed),
        "updated_at": timezone.now().isoformat(),
        "updated_by": str(user.pk),
    }
    state.exercise_progress = progress
    state.save(update_fields=["exercise_progress", "updated_at"])
    return state
