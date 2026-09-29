from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.pos.models import Order
from apps.pos.services import close_pos_shift, open_pos_shift, record_order_payment, record_order_refund
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
from apps.purchasing.services import receive_purchase_order_goods
from apps.tenants.models import Outlet, OutletType, Site, Tenant

from .models import CashbookEntry, FinanceCategoryKind, FinancePostingLink, FinancePostingSource


class PosFinancePostingTests(TestCase):
    def setUp(self) -> None:
        self.tenant = Tenant.objects.create(name="POS Finance Tenant", slug="pos-finance-tenant")
        self.site = Site.objects.create(tenant=self.tenant, name="Main Site")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Main Bar",
            outlet_type=OutletType.BAR,
        )
        self.user = User.objects.create_user(email="pos-finance@test.local", password="TestPass9!")
        self.order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            currency="USD",
            subtotal=Decimal("10.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("10.00"),
        )

    def test_payment_posts_income_once_and_replay_is_idempotent(self) -> None:
        payment, replay = record_order_payment(
            order=self.order,
            user=self.user,
            amount=Decimal("10.00"),
            method="cash",
            idempotency_key="pos-pay-1",
        )
        self.assertFalse(replay)
        self.assertEqual(CashbookEntry.objects.count(), 1)
        entry = CashbookEntry.objects.get()
        self.assertEqual(entry.category.kind, FinanceCategoryKind.INCOME)
        self.assertEqual(entry.amount, Decimal("10.00"))
        self.assertEqual(entry.site_id, self.site.id)
        self.assertEqual(entry.reference, self.order.bill_reference)
        self.assertEqual(
            FinancePostingLink.objects.filter(
                tenant=self.tenant,
                source_type=FinancePostingSource.POS_PAYMENT,
                source_id=str(payment.id),
            ).count(),
            1,
        )

        replay_payment, replay_flag = record_order_payment(
            order=self.order,
            user=self.user,
            amount=Decimal("10.00"),
            method="cash",
            idempotency_key="pos-pay-1",
        )
        self.assertTrue(replay_flag)
        self.assertEqual(replay_payment.id, payment.id)
        self.assertEqual(CashbookEntry.objects.count(), 1)


    def test_payment_replay_rejects_changed_tender(self) -> None:
        record_order_payment(order=self.order, user=self.user, amount=Decimal("5.00"), method="cash", idempotency_key="pay-change")
        with self.assertRaises(ValidationError):
            record_order_payment(order=self.order, user=self.user, amount=Decimal("6.00"), method="cash", idempotency_key="pay-change")
        with self.assertRaises(ValidationError):
            record_order_payment(order=self.order, user=self.user, amount=Decimal("5.00"), method="card", idempotency_key="pay-change")
        self.assertEqual(self.order.payments.count(), 1)

    def test_shift_cash_expected_balance_deducts_refunds(self) -> None:
        shift = open_pos_shift(tenant_id=self.tenant.id, outlet=self.outlet, user=self.user, opening_cash=Decimal("20"))
        record_order_payment(order=self.order, user=self.user, amount=Decimal("10"), method="cash", idempotency_key="shift-payment")
        record_order_refund(order=self.order, user=self.user, amount=Decimal("4"), reason="Return", idempotency_key="shift-refund", restock=False)
        closed = close_pos_shift(shift=shift, user=self.user, counted_cash=Decimal("26"))
        self.assertEqual(closed.expected_cash, Decimal("26.00"))

    def test_refund_replay_rejects_changed_amount_or_restock(self) -> None:
        record_order_payment(order=self.order, user=self.user, amount=Decimal("10"), method="cash", idempotency_key="refund-pay")
        record_order_refund(order=self.order, user=self.user, amount=Decimal("4"), reason="Return", idempotency_key="refund-key", restock=False)
        with self.assertRaises(ValidationError):
            record_order_refund(order=self.order, user=self.user, amount=Decimal("5"), reason="Return", idempotency_key="refund-key", restock=False)
        with self.assertRaises(ValidationError):
            record_order_refund(order=self.order, user=self.user, amount=Decimal("4"), reason="Return", idempotency_key="refund-key", restock=True)
        self.assertEqual(self.order.refunds.count(), 1)


class PurchaseFinancePostingTests(TestCase):
    def setUp(self) -> None:
        self.tenant = Tenant.objects.create(name="Purchase Finance Tenant", slug="po-finance-tenant")
        self.site = Site.objects.create(tenant=self.tenant, name="Store Site")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Warehouse",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="po-finance@test.local", password="TestPass9!")
        self.membership = Membership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self.supplier = Supplier.objects.create(tenant=self.tenant, name="Supply Co")
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Inventory")
        self.menu_item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Soda Crate",
            track_inventory=True,
            unit_price=Decimal("1.00"),
        )

    def test_receive_posts_expense_for_costed_line(self) -> None:
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            outlet=self.outlet,
            status=PurchaseOrderStatus.SENT,
            reference="PO-001",
            created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            menu_item=self.menu_item,
            quantity_ordered=Decimal("5"),
            quantity_received=Decimal("0"),
            unit_cost=Decimal("2.50"),
        )
        receive_purchase_order_goods(
            po=po,
            lines_payload=[{"line_id": line.id, "quantity": Decimal("2")}],
            user=self.user,
            membership=self.membership,
        )
        self.assertEqual(CashbookEntry.objects.count(), 1)
        entry = CashbookEntry.objects.get()
        self.assertEqual(entry.category.kind, FinanceCategoryKind.EXPENSE)
        self.assertEqual(entry.amount, Decimal("5.00"))
        self.assertEqual(entry.reference, "PO-001")
        self.assertEqual(entry.site_id, self.site.id)
        self.assertEqual(entry.transaction_date, date.today())
        self.assertEqual(
            FinancePostingLink.objects.filter(
                tenant=self.tenant,
                source_type=FinancePostingSource.PURCHASE_RECEIVE_MOVEMENT,
            ).count(),
            1,
        )

    def test_receive_skips_expense_posting_without_unit_cost(self) -> None:
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            outlet=self.outlet,
            status=PurchaseOrderStatus.SENT,
            reference="PO-002",
            created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            menu_item=self.menu_item,
            quantity_ordered=Decimal("3"),
            quantity_received=Decimal("0"),
            unit_cost=None,
        )
        receive_purchase_order_goods(
            po=po,
            lines_payload=[{"line_id": line.id, "quantity": Decimal("1")}],
            user=self.user,
            membership=self.membership,
        )
        self.assertEqual(CashbookEntry.objects.count(), 0)
