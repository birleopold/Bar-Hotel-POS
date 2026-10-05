from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import StringIO
import json

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance
from apps.lodging.models import Folio, FolioLine
from apps.pos.models import Order, OrderLine
from apps.pos.services import close_pos_shift, open_pos_shift, process_supermarket_line_return, record_order_payment, record_order_refund, refund_retail_line
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
<<<<<<< HEAD
from apps.purchasing.services import confirm_missing_unit_cost, receive_purchase_order_goods, record_supplier_payment
from apps.tenants.models import Outlet, OutletType, Site, Tenant
=======
from apps.purchasing.services import receive_purchase_order_goods
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings
>>>>>>> c13650f (if i had a supermarket or retail shop, can the POS alone act as if its a quickbooks point of sale system without the client ever knowing there has ever been bar hotel attached, and vice versa for an independent hotel or bar)

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

    def _add_tracked_sale(self):
        category = MenuCategory.objects.create(tenant=self.tenant, name="Goods")
        item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Bottle", unit_price=Decimal("10"), track_inventory=True)
        line = OrderLine.objects.create(order=self.order, menu_item=item, label=item.name, quantity=Decimal("1"), unit_price=Decimal("10"), line_total=Decimal("10"), kds_status="ready")
        balance = StockBalance.objects.create(tenant=self.tenant, outlet=self.outlet, menu_item=item, quantity=Decimal("1"))
        return line, balance

    def test_final_split_tender_refund_restocks_actual_sale_once(self) -> None:
        _line, balance = self._add_tracked_sale()
        cash, _ = record_order_payment(order=self.order, user=self.user, amount=Decimal("4"), method="cash", idempotency_key="split-cash")
        card, _ = record_order_payment(order=self.order, user=self.user, amount=Decimal("6"), method="card", idempotency_key="split-card")
        record_order_refund(order=self.order, user=self.user, amount=Decimal("4"), reason="Return", idempotency_key="split-refund-cash", restock=False, payment_id=cash.id)
        record_order_refund(order=self.order, user=self.user, amount=Decimal("6"), reason="Return", idempotency_key="split-refund-card", restock=True, payment_id=card.id)
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("1"))

    def test_refund_does_not_restock_items_already_returned(self) -> None:
        line, balance = self._add_tracked_sale()
        record_order_payment(order=self.order, user=self.user, amount=Decimal("10"), method="cash", idempotency_key="returned-payment")
        process_supermarket_line_return(order=self.order, line=line, quantity=Decimal("0.5"), reason="Return", restock=True, user=self.user)
        record_order_refund(order=self.order, user=self.user, amount=Decimal("10"), reason="Return", idempotency_key="returned-refund", restock=True)
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("1"))

    def test_line_return_cannot_restock_after_order_refund_restock(self) -> None:
        line, balance = self._add_tracked_sale()
        record_order_payment(order=self.order, user=self.user, amount=Decimal("10"), method="cash", idempotency_key="fully-refunded-payment")
        record_order_refund(order=self.order, user=self.user, amount=Decimal("10"), reason="Return", idempotency_key="fully-refunded-refund", restock=True)
        with self.assertRaises(ValidationError):
            process_supermarket_line_return(order=self.order, line=line, quantity=Decimal("1"), reason="Return", restock=True, user=self.user)
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("1"))

    def test_legacy_audit_lists_uncredited_folio_without_changing_it(self) -> None:
        folio = Folio.objects.create(tenant=self.tenant, site=self.site, guest_name="Guest", currency="USD")
        self.order.folio = folio
        self.order.is_paid = True
        self.order.status = "closed"
        self.order.save(update_fields=["folio", "is_paid", "status", "updated_at"])
        FolioLine.objects.create(tenant=self.tenant, folio=folio, amount=Decimal("10"), description="Old POS", source_order=self.order)
        out = StringIO()
        call_command("audit_legacy_postings", tenant_id=str(self.tenant.id), stdout=out)
        self.assertEqual(json.loads(out.getvalue())["paid_pos_orders_with_uncredited_folio_lines"], [str(self.order.id)])
        self.assertEqual(folio.lines.count(), 1)

    def test_return_restock_uses_original_sale_even_if_catalog_flag_changes(self) -> None:
        line, balance = self._add_tracked_sale()
        record_order_payment(order=self.order, user=self.user, amount=Decimal("10"), method="cash", idempotency_key="flag-change-pay")
        line.menu_item.track_inventory = False
        line.menu_item.save(update_fields=["track_inventory", "updated_at"])
        process_supermarket_line_return(order=self.order, line=line, quantity=Decimal("1"), reason="Unopened", restock=True, user=self.user)
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("1"))

    def test_return_cannot_add_stock_for_untracked_sale(self) -> None:
        category = MenuCategory.objects.create(tenant=self.tenant, name="Services")
        item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Fee", unit_price=Decimal("10"), track_inventory=False)
        line = OrderLine.objects.create(order=self.order, menu_item=item, label=item.name, quantity=Decimal("1"), unit_price=Decimal("10"), line_total=Decimal("10"), kds_status="ready")
        record_order_payment(order=self.order, user=self.user, amount=Decimal("10"), method="cash", idempotency_key="untracked-pay")
        with self.assertRaises(ValidationError):
            process_supermarket_line_return(order=self.order, line=line, quantity=Decimal("1"), reason="", restock=True, user=self.user)
        self.assertFalse(self.order.supermarket_returns.exists())

    def test_retail_refund_links_tender_quantity_and_stock_once(self) -> None:
        self.outlet.outlet_type = OutletType.RETAIL
        self.outlet.save(update_fields=["outlet_type", "updated_at"])
        line, balance = self._add_tracked_sale()
        cash, _ = record_order_payment(order=self.order, user=self.user, amount=Decimal("4"), method="cash", idempotency_key="retail-cash")
        card, _ = record_order_payment(order=self.order, user=self.user, amount=Decimal("6"), method="card", idempotency_key="retail-card")
        ret, replay = refund_retail_line(order=self.order, line=line, quantity=Decimal("0.5"), amount=Decimal("4"), reason="Unopened", restock=True, user=self.user, payment_id=cash.id, idempotency_key="retail-return")
        self.assertFalse(replay)
        self.assertEqual(ret.refund.payment_id, cash.id)
        self.assertEqual(ret.refund.amount, Decimal("4"))
        self.assertFalse(ret.refund.restocked)
        again, replay = refund_retail_line(order=self.order, line=line, quantity=Decimal("0.5"), amount=Decimal("4"), reason="Unopened", restock=True, user=self.user, payment_id=cash.id, idempotency_key="retail-return")
        self.assertTrue(replay)
        self.assertEqual(again.id, ret.id)
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("0.5"))
        self.assertEqual(self.order.refunds.count(), 1)
        self.assertEqual(self.order.supermarket_returns.count(), 1)
        with self.assertRaises(ValidationError):
            refund_retail_line(order=self.order, line=line, quantity=Decimal("1"), amount=Decimal("4"), reason="Unopened", restock=True, user=self.user, payment_id=cash.id, idempotency_key="retail-return")
        with self.assertRaises(ValidationError):
            refund_retail_line(order=self.order, line=line, quantity=Decimal("1"), amount=Decimal("5"), reason="Unopened", restock=True, user=self.user, payment_id=card.id, idempotency_key="retail-invalid")
        self.assertEqual(self.order.refunds.count(), 1)

    def test_retail_refund_rolls_back_cash_when_stock_return_invalid(self) -> None:
        self.outlet.outlet_type = OutletType.SUPERMARKET
        self.outlet.save(update_fields=["outlet_type", "updated_at"])
        line, _balance = self._add_tracked_sale()
        record_order_payment(order=self.order, user=self.user, amount=Decimal("10"), method="cash", idempotency_key="rollback-pay")
        with self.assertRaises(ValidationError):
            refund_retail_line(order=self.order, line=line, quantity=Decimal("2"), amount=Decimal("3"), reason="Too many", restock=True, user=self.user, idempotency_key="rollback-refund")
        self.assertFalse(self.order.refunds.exists())
        self.assertFalse(self.order.supermarket_returns.exists())
        self.assertEqual(CashbookEntry.objects.filter(category__kind=FinanceCategoryKind.EXPENSE).count(), 0)

    def test_retail_refund_api_requires_manager_and_replays_without_extra_posting(self) -> None:
        self.outlet.outlet_type = OutletType.RETAIL
        self.outlet.save(update_fields=["outlet_type", "updated_at"])
        line, _balance = self._add_tracked_sale()
        record_order_payment(order=self.order, user=self.user, amount=Decimal("10"), method="cash", idempotency_key="api-retail-pay")
        member = Membership.objects.create(tenant=self.tenant, user=self.user, role=MembershipRole.SERVER)
        client = APIClient()
        client.force_login(self.user)
        headers = {"HTTP_X_TENANT_ID": str(self.tenant.id), "HTTP_IDEMPOTENCY_KEY": "api-retail-refund"}
        url = f"/api/v1/orders/{self.order.id}/retail-line-refunds/"
        payload = {"line_id": str(line.id), "quantity": "1", "amount": "10.00", "reason": "Damaged", "restock": False}
        self.assertEqual(client.post(url, payload, format="json", **headers).status_code, 403)
        member.role = MembershipRole.OWNER
        member.save(update_fields=["role", "updated_at"])
        first = client.post(url, payload, format="json", **headers)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["refund"]["amount"], "10.00")
        self.assertEqual(client.post(url, payload, format="json", **headers).status_code, 200)
        self.assertEqual(self.order.refunds.count(), 1)
        self.assertEqual(self.order.supermarket_returns.count(), 1)
        self.assertEqual(CashbookEntry.objects.filter(category__kind=FinanceCategoryKind.EXPENSE).count(), 1)


class PurchaseFinancePostingTests(TestCase):
    def setUp(self) -> None:
        self.tenant = Tenant.objects.create(name="Purchase Finance Tenant", slug="po-finance-tenant")
        self.site = Site.objects.create(tenant=self.tenant, name="Store Site")
        TenantSettings.objects.create(tenant=self.tenant, business_lines=["supermarket"], enabled_staff_modules=["pos", "inventory", "purchasing", "finance", "workspace"])
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

    def test_receipt_is_not_cash_expense_and_supplier_payment_posts_once(self) -> None:
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
        self.assertEqual(CashbookEntry.objects.count(), 0)
        payment, replay = record_supplier_payment(
            po=po, amount=Decimal("3.00"), method="bank", reference="BANK-1",
            idempotency_key="supplier-pay-1", user=self.user, membership=self.membership,
        )
        self.assertFalse(replay)
        entry = CashbookEntry.objects.get()
        self.assertEqual(entry.category.kind, FinanceCategoryKind.EXPENSE)
        self.assertEqual(entry.amount, Decimal("3.00"))
        self.assertEqual(entry.reference, "BANK-1")
        self.assertEqual(entry.site_id, self.site.id)
        self.assertEqual(entry.transaction_date, date.today())
        self.assertEqual(
            FinancePostingLink.objects.filter(
                tenant=self.tenant,
                source_type=FinancePostingSource.SUPPLIER_PAYMENT,
                source_id=str(payment.id),
            ).count(),
            1,
        )
        again, replay = record_supplier_payment(
            po=po, amount=Decimal("3.00"), method="bank", reference="BANK-1",
            idempotency_key="supplier-pay-1", user=self.user, membership=self.membership,
        )
        self.assertTrue(replay)
        self.assertEqual(again.id, payment.id)
        self.assertEqual(CashbookEntry.objects.count(), 1)
        with self.assertRaises(ValidationError):
            record_supplier_payment(
                po=po, amount=Decimal("3.01"), method="bank", reference="BANK-1",
                idempotency_key="supplier-pay-1", user=self.user, membership=self.membership,
            )
        with self.assertRaises(ValidationError):
            record_supplier_payment(
                po=po, amount=Decimal("2.01"), method="cash", reference="CASH-2",
                idempotency_key="supplier-pay-2", user=self.user, membership=self.membership,
            )

    def test_legacy_receipt_posting_blocks_new_supplier_payment(self) -> None:
        po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=self.supplier, outlet=self.outlet,
            status=PurchaseOrderStatus.SENT, reference="OLD-PO", created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=self.menu_item,
            quantity_ordered=Decimal("2"), unit_cost=Decimal("4"),
        )
        receive_purchase_order_goods(
            po=po, lines_payload=[{"line_id": line.id, "quantity": Decimal("1")}],
            user=self.user, membership=self.membership,
        )
        from apps.inventory.models import StockMovement
        from .services import post_cashbook_for_source
        movement = StockMovement.objects.get(purchase_order=po)
        post_cashbook_for_source(
            tenant_id=self.tenant.id, source_type=FinancePostingSource.PURCHASE_RECEIVE_MOVEMENT,
            source_id=str(movement.id), kind=FinanceCategoryKind.EXPENSE,
            amount=Decimal("4"), site=self.site,
        )
        with self.assertRaises(ValidationError):
            record_supplier_payment(
                po=po, amount=Decimal("4"), method="cash", reference="",
                idempotency_key="old-po-pay", user=self.user, membership=self.membership,
            )
        self.assertEqual(CashbookEntry.objects.count(), 1)

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
        with self.assertRaises(ValidationError):
            record_supplier_payment(
                po=po, amount=Decimal("1"), method="cash", reference="",
                idempotency_key="no-cost", user=self.user, membership=self.membership,
            )
        confirm_missing_unit_cost(
            po=po, line_id=line.id, unit_cost=Decimal("2.50"),
            user=self.user, membership=self.membership,
        )
        record_supplier_payment(
            po=po, amount=Decimal("2.50"), method="cash", reference="",
            idempotency_key="cost-confirmed-pay", user=self.user, membership=self.membership,
        )
        with self.assertRaises(ValidationError):
            confirm_missing_unit_cost(
                po=po, line_id=line.id, unit_cost=Decimal("3"),
                user=self.user, membership=self.membership,
            )

    def test_duplicate_receive_line_does_not_double_count_stock(self) -> None:
        po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=self.supplier, outlet=self.outlet,
            status=PurchaseOrderStatus.SENT, created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=self.menu_item,
            quantity_ordered=Decimal("3"), unit_cost=Decimal("2"),
        )
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po, lines_payload=[
                    {"line_id": line.id, "quantity": Decimal("1")},
                    {"line_id": line.id, "quantity": Decimal("1")},
                ], user=self.user, membership=self.membership,
            )
        line.refresh_from_db()
        self.assertEqual(line.quantity_received, Decimal("0"))
        self.assertFalse(po.receipts.exists())

    def test_supplier_payment_api_requires_key_and_returns_same_record_on_retry(self) -> None:
        po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=self.supplier, outlet=self.outlet,
            status=PurchaseOrderStatus.SENT, created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=self.menu_item,
            quantity_ordered=Decimal("2"), unit_cost=Decimal("4"),
        )
        receive_purchase_order_goods(
            po=po, lines_payload=[{"line_id": line.id, "quantity": Decimal("1")}],
            user=self.user, membership=self.membership,
        )
        client = APIClient()
        self.assertTrue(client.login(username=self.user.email, password="TestPass9!"))
        url = f"/api/v1/purchasing/purchase-orders/{po.id}/payments/"
        payload = {"amount": "4.00", "method": "bank", "reference": "REF-1"}
        scope = {"HTTP_X_TENANT_ID": str(self.tenant.id)}
        self.assertEqual(client.post(url, payload, format="json", **scope).status_code, 400)
        headers = {**scope, "HTTP_IDEMPOTENCY_KEY": "po-api-pay-1"}
        first = client.post(url, payload, format="json", **headers)
        self.assertEqual(first.status_code, 201, first.content)
        retry = client.post(url, payload, format="json", **headers)
        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(first.data["id"], retry.data["id"])
        self.assertEqual(CashbookEntry.objects.count(), 1)
