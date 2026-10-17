"""Supplier invoice behaviour: document recording never invents a payment."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.catalog.models import MenuCategory, MenuItem
from apps.purchasing.models import (
    Supplier, PurchaseOrder, PurchaseOrderLine, SupplierInvoice,
    PurchaseOrderStatus, SupplierPayment,
)
from apps.purchasing.services import record_supplier_invoice
from apps.purchasing.services_exposure import purchase_order_exposure
from apps.tenants.models import Site, Tenant, Outlet, OutletType


class SupplierInvoiceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Invoice Tenant", slug="invoice-tenant-tests")
        site = Site.objects.create(tenant=self.tenant, name="Warehouse")
        self.outlet = Outlet.objects.create(site=site, name="Main", outlet_type=OutletType.RETAIL)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Consumables")
        item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Coffee",
            unit_price=Decimal("5000"), track_inventory=True,
        )
        supplier = Supplier.objects.create(tenant=self.tenant, name="Vendor")
        self.po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=supplier, outlet=self.outlet,
            status=PurchaseOrderStatus.PARTIALLY_RECEIVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=self.po, menu_item=item, quantity_ordered=Decimal("5"),
            quantity_received=Decimal("2"), unit_cost=Decimal("1000"),
        )

    def record(self, *, reference="INV-001", amount=Decimal("1500")):
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            return record_supplier_invoice(
                po=self.po, reference=reference,
                invoice_date=date(2026, 10, 1), due_date=date(2026, 10, 30),
                amount=amount, note="", user=None, membership=object(),
            )

    def test_document_is_idempotent_and_does_not_pay_supplier(self):
        first, replay = self.record()
        second, replay2 = self.record()
        self.assertFalse(replay)
        self.assertTrue(replay2)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SupplierInvoice.objects.filter(purchase_order=self.po).count(), 1)
        self.assertFalse(SupplierPayment.objects.filter(purchase_order=self.po).exists())
        rows = purchase_order_exposure(tenant=self.tenant, outlet_ids=[self.outlet.pk])
        self.assertEqual(rows[0]["invoiced_value"], Decimal("1500"))
        self.assertEqual(rows[0]["unbilled_received_value"], Decimal("500"))
        self.assertEqual(rows[0]["unpaid_invoiced_value"], Decimal("1500"))
        self.assertEqual(rows[0]["earliest_invoice_due_date"], date(2026, 10, 30))

    def test_prevent_duplicate_reference_with_changed_amount(self):
        self.record()
        with self.assertRaises(ValidationError):
            self.record(amount=Decimal("1750"))

    def test_total_invoices_cannot_exceed_received_goods(self):
        self.record()
        with self.assertRaises(ValidationError):
            self.record(reference="INV-002", amount=Decimal("501"))

    def test_permission_check_rejects_unassigned_outlet(self):
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=False):
            with self.assertRaises(ValidationError):
                record_supplier_invoice(
                    po=self.po, reference="INV-OTHER",
                    invoice_date=date(2026, 10, 1), due_date=date(2026, 11, 1),
                    amount=Decimal("100"), user=None, membership=object(),
                )
        self.assertFalse(SupplierInvoice.objects.filter(purchase_order=self.po).exists())

    def test_recorded_invoice_caps_payment_but_not_received_balance(self):
        """A partial invoice cannot authorize paying the uninvoiced receipt remainder."""
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services import record_supplier_payment

        self.record(amount=Decimal("1500"))
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense") as post_expense:
                with self.assertRaisesRegex(ValidationError, "unpaid recorded supplier invoices"):
                    record_supplier_payment(
                        po=self.po, amount=Decimal("1500.01"),
                        method=SupplierPaymentMethod.CASH, reference="paid-overshoot",
                        idempotency_key="payment-overshoot", user=None, membership=object(),
                    )
                self.assertFalse(SupplierPayment.objects.filter(purchase_order=self.po).exists())
                post_expense.assert_not_called()
                payment, replay = record_supplier_payment(
                    po=self.po, amount=Decimal("1500.00"),
                    method=SupplierPaymentMethod.CASH, reference="paid-invoice",
                    idempotency_key="payment-invoice", user=None, membership=object(),
                )
                self.assertFalse(replay)
                self.assertEqual(payment.amount, Decimal("1500.00"))
                post_expense.assert_called_once()
                exposure = purchase_order_exposure(tenant=self.tenant, outlet_ids=[self.outlet.pk])
                self.assertEqual(exposure[0]["unpaid_invoiced_value"], Decimal("0"))
                self.assertEqual(exposure[0]["unbilled_received_value"], Decimal("500"))

    def test_receipt_backed_payment_without_invoices_remains_available(self):
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services import record_supplier_payment

        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense") as post_expense:
                payment, replay = record_supplier_payment(
                    po=self.po, amount=Decimal("2000.00"),
                    method=SupplierPaymentMethod.BANK, reference="legacy-receipt",
                    idempotency_key="legacy-no-invoice", user=None, membership=object(),
                )
        self.assertFalse(replay)
        self.assertEqual(payment.amount, Decimal("2000.00"))
        post_expense.assert_called_once()

    def test_invoice_amount_guard_rejects_invalid_decimal_inputs_without_payment(self):
        for raw in ("NaN", "Infinity", "-1", "0", "12.123", "abc", "1000000000000.00", None):
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    self.record(reference="BAD-INVOICE", amount=raw)
        self.assertFalse(SupplierInvoice.objects.filter(purchase_order=self.po).exists())
        self.assertFalse(SupplierPayment.objects.filter(purchase_order=self.po).exists())
        invoice, replay = self.record(reference="GOOD-INVOICE", amount="1234.50")
        self.assertFalse(replay)
        self.assertEqual(invoice.amount, Decimal("1234.50"))

    def test_supplier_invoice_invalid_date_does_not_create_document(self):
        for issued, due in ((None, date(2026, 10, 30)), (date(2026, 10, 1), None),
                            (date(2026, 10, 30), date(2026, 10, 1))):
            with self.subTest(issued=issued, due=due):
                with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
                    with self.assertRaises(ValidationError):
                        record_supplier_invoice(
                            po=self.po, reference="BAD-DATE",
                            invoice_date=issued, due_date=due, amount=Decimal("50"),
                            user=None, membership=object(),
                        )
        self.assertFalse(SupplierInvoice.objects.filter(purchase_order=self.po).exists())

    def test_missing_unit_cost_confirmation_guards_numeric_input(self):
        from apps.purchasing.services import confirm_missing_unit_cost
        line = PurchaseOrderLine.objects.get(purchase_order=self.po)
        line.unit_cost = None
        line.save(update_fields=["unit_cost"])
        for value in ("NaN", "Infinity", "-1", "1.001", "abc", "10000000000.00", None):
            with self.subTest(value=value):
                with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
                    with self.assertRaises(ValidationError):
                        confirm_missing_unit_cost(
                            po=self.po, line_id=line.pk, unit_cost=value,
                            user=None, membership=object(),
                        )
                line.refresh_from_db()
                self.assertIsNone(line.unit_cost)
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            result = confirm_missing_unit_cost(
                po=self.po, line_id=line.pk, unit_cost="123.45",
                user=None, membership=object(),
            )
        self.assertEqual(result.unit_cost, Decimal("123.45"))

    def test_supplier_credit_reduces_payable_without_posting_cash_or_stock(self):
        from apps.purchasing.services import record_supplier_credit_note, record_supplier_payment
        from apps.purchasing.models import SupplierPaymentMethod
        invoice, _ = self.record(reference="INV-CREDIT", amount=Decimal("1500"))
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            credit, replay = record_supplier_credit_note(
                po=self.po, invoice_id=invoice.pk, reference="CN-001",
                credit_date=date(2026, 10, 4), amount=Decimal("500"),
                reason="Supplier credited an incorrect delivery charge.",
                user=None, membership=object(),
            )
            same, repeated = record_supplier_credit_note(
                po=self.po, invoice_id=invoice.pk, reference="CN-001",
                credit_date=date(2026, 10, 4), amount=Decimal("500"),
                reason="Supplier credited an incorrect delivery charge.",
                user=None, membership=object(),
            )
            self.assertFalse(replay)
            self.assertTrue(repeated)
            self.assertEqual(credit.pk, same.pk)
            self.assertFalse(SupplierPayment.objects.filter(purchase_order=self.po).exists())
            with self.assertRaises(ValidationError):
                record_supplier_credit_note(
                    po=self.po, invoice_id=invoice.pk, reference="CN-002",
                    credit_date=date(2026, 10, 5), amount=Decimal("1001"),
                    reason="This credit is more than the outstanding document.",
                    user=None, membership=object(),
                )
            rows = purchase_order_exposure(tenant=self.tenant, outlet_ids=[self.outlet.pk])
            self.assertEqual(rows[0]["credited_value"], Decimal("500"))
            self.assertEqual(rows[0]["net_invoiced_value"], Decimal("1000"))
            self.assertEqual(rows[0]["unpaid_invoiced_value"], Decimal("1000"))
            with patch("apps.purchasing.services.post_supplier_payment_expense") as record_expense:
                with self.assertRaises(ValidationError):
                    record_supplier_payment(
                        po=self.po, amount=Decimal("1000.01"),
                        method=SupplierPaymentMethod.CASH, reference="too-large",
                        idempotency_key="pay-over-credit", user=None, membership=object(),
                    )
                record_expense.assert_not_called()
                payment, _ = record_supplier_payment(
                    po=self.po, amount=Decimal("1000"),
                    method=SupplierPaymentMethod.CASH, reference="settled",
                    idempotency_key="pay-credit", user=None, membership=object(),
                )
                self.assertEqual(payment.amount, Decimal("1000"))
                record_expense.assert_called_once()
            self.assertEqual(purchase_order_exposure(
                tenant=self.tenant, outlet_ids=[self.outlet.pk],
            )[0]["unpaid_invoiced_value"], Decimal("0"))

    def test_credit_does_not_allow_cross_order_invoice_or_post_payment_refund(self):
        from apps.purchasing.services import record_supplier_credit_note
        invoice, _ = self.record(reference="INV-SCOPE", amount=Decimal("1500"))
        other_order = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=self.po.supplier,
            outlet=self.outlet, status=PurchaseOrderStatus.PARTIALLY_RECEIVED,
        )
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with self.assertRaises(ValidationError):
                record_supplier_credit_note(
                    po=other_order, invoice_id=invoice.pk, reference="CROSS",
                    credit_date=date(2026, 10, 4), amount=Decimal("10"),
                    reason="Invoice belongs to a different purchase order.",
                    user=None, membership=object(),
                )
            with self.assertRaises(ValidationError):
                record_supplier_credit_note(
                    po=self.po, invoice_id=invoice.pk, reference="BAD-NAN",
                    credit_date=date(2026, 10, 4), amount="NaN",
                    reason="An invalid credit should never be recorded.",
                    user=None, membership=object(),
                )


    def test_invoice_linked_payment_has_exact_balance_and_idempotency(self):
        from apps.purchasing.services import record_supplier_payment
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services_exposure import supplier_invoice_settlement_rows

        invoice, _ = self.record(reference="LINK-01", amount=Decimal("1200"))
        self.record(reference="LINK-02", amount=Decimal("500"))
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense") as expense:
                payment, replay = record_supplier_payment(
                    po=self.po, amount=Decimal("450"), method=SupplierPaymentMethod.BANK,
                    reference="bank-transfer", idempotency_key="invoice-linked-450",
                    invoice_id=invoice.pk, user=None, membership=object(),
                )
                same, repeated = record_supplier_payment(
                    po=self.po, amount=Decimal("450"), method=SupplierPaymentMethod.BANK,
                    reference="bank-transfer", idempotency_key="invoice-linked-450",
                    invoice_id=invoice.pk, user=None, membership=object(),
                )
                self.assertFalse(replay)
                self.assertTrue(repeated)
                self.assertEqual(same.pk, payment.pk)
                self.assertEqual(payment.invoice_id, invoice.pk)
                expense.assert_called_once()
                with self.assertRaisesRegex(ValidationError, "unpaid balance"):
                    record_supplier_payment(
                        po=self.po, amount=Decimal("751"), method=SupplierPaymentMethod.CASH,
                        reference="another", idempotency_key="invoice-overpay",
                        invoice_id=invoice.pk, user=None, membership=object(),
                    )
        rows, unallocated = supplier_invoice_settlement_rows(po=self.po, today=date(2026, 11, 2))
        self.assertEqual(unallocated, Decimal("0"))
        self.assertTrue(rows[0]["is_exact"])
        self.assertEqual(rows[0]["paid"], Decimal("450"))
        self.assertEqual(rows[0]["unpaid"], Decimal("750"))
        self.assertEqual(rows[0]["overdue_days"], 3)

    def test_payment_cannot_be_attributed_to_a_different_order_invoice(self):
        from apps.purchasing.services import record_supplier_payment
        from apps.purchasing.models import SupplierPaymentMethod

        another_po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=self.po.supplier, outlet=self.outlet,
            status=PurchaseOrderStatus.PARTIALLY_RECEIVED,
        )
        other_invoice = SupplierInvoice.objects.create(
            tenant=self.tenant, purchase_order=another_po, reference="OTHER",
            invoice_date=date(2026, 10, 1), due_date=date(2026, 11, 1),
            amount=Decimal("100"),
        )
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with self.assertRaisesRegex(ValidationError, "belonging"):
                record_supplier_payment(
                    po=self.po, amount=Decimal("100"), method=SupplierPaymentMethod.CASH,
                    reference="bad", idempotency_key="not-our-invoice",
                    invoice_id=other_invoice.pk, user=None, membership=object(),
                )
        self.assertFalse(SupplierPayment.objects.filter(purchase_order=self.po).exists())

    def test_credit_cannot_erase_amount_already_paid_to_invoice(self):
        from apps.purchasing.services import record_supplier_payment, record_supplier_credit_note
        from apps.purchasing.models import SupplierPaymentMethod

        invoice, _ = self.record(reference="PAID-INV", amount=Decimal("1500"))
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense"):
                record_supplier_payment(
                    po=self.po, amount=Decimal("1100"), method=SupplierPaymentMethod.BANK,
                    reference="bank-01", idempotency_key="paid-1100",
                    invoice_id=invoice.pk, user=None, membership=object(),
                )
            with self.assertRaisesRegex(ValidationError, "unpaid balance"):
                record_supplier_credit_note(
                    po=self.po, invoice_id=invoice.pk, reference="CREDIT-TOO-HIGH",
                    credit_date=date(2026, 10, 10), amount=Decimal("401"),
                    reason="Over-credit must not undo already settled funds.",
                    user=None, membership=object(),
                )
            credit, replay = record_supplier_credit_note(
                po=self.po, invoice_id=invoice.pk, reference="CREDIT-VALID",
                credit_date=date(2026, 10, 10), amount=Decimal("400"),
                reason="Supplier issued a valid credit against the unpaid remainder.",
                user=None, membership=object(),
            )
            self.assertFalse(replay)
            self.assertEqual(credit.amount, Decimal("400"))

    def test_unassigned_legacy_payment_is_not_assumed_to_pay_selected_invoice(self):
        from apps.purchasing.services import record_supplier_payment
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services_exposure import supplier_invoice_settlement_rows

        invoice, _ = self.record(reference="UNLINKED-INVOICE", amount=Decimal("1500"))
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense"):
                record_supplier_payment(
                    po=self.po, amount=Decimal("200"), method=SupplierPaymentMethod.CASH,
                    reference="old-payment", idempotency_key="legacy-unlinked",
                    user=None, membership=object(),
                )
                with self.assertRaisesRegex(ValidationError, "Reconcile"):
                    record_supplier_payment(
                        po=self.po, amount=Decimal("200"), method=SupplierPaymentMethod.CASH,
                        reference="new-payment", idempotency_key="selected-with-legacy",
                        invoice_id=invoice.pk, user=None, membership=object(),
                    )
        rows, unallocated = supplier_invoice_settlement_rows(po=self.po)
        self.assertEqual(unallocated, Decimal("200"))
        self.assertFalse(rows[0]["is_exact"])
        self.assertEqual(rows[0]["unpaid"], Decimal("1500"))


    def test_purchase_api_invoice_fields_do_not_invent_legacy_payment_allocation(self):
        from apps.purchasing.serializers import SupplierInvoiceReadSerializer
        from apps.purchasing.services import record_supplier_payment
        from apps.purchasing.models import SupplierPaymentMethod

        invoice, _ = self.record(reference="API-BILL", amount=Decimal("1400"))
        data = SupplierInvoiceReadSerializer(invoice).data
        self.assertEqual(data["credited_amount"], "0.00")
        self.assertEqual(data["linked_payments_amount"], "0.00")
        self.assertEqual(data["unpaid_amount"], "1400.00")
        self.assertFalse(data["unlinked_payment_warning"])
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense"):
                record_supplier_payment(
                    po=self.po, amount=Decimal("200"), method=SupplierPaymentMethod.BANK,
                    reference="bank-legacy", idempotency_key="unassigned-api",
                    user=None, membership=object(),
                )
        unresolved = SupplierInvoiceReadSerializer(invoice).data
        self.assertTrue(unresolved["unlinked_payment_warning"])
        self.assertIsNone(unresolved["unpaid_amount"])
        self.assertIsNone(unresolved["overdue_days"])

    def test_idempotency_key_cannot_be_reused_for_another_invoice(self):
        from apps.purchasing.services import record_supplier_payment
        from apps.purchasing.models import SupplierPaymentMethod

        invoice, _ = self.record(reference="IDEMP-ONE", amount=Decimal("1000"))
        another, _ = self.record(reference="IDEMP-TWO", amount=Decimal("500"))
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense") as posting:
                record_supplier_payment(
                    po=self.po, amount=Decimal("100"), method=SupplierPaymentMethod.BANK,
                    reference="ref", idempotency_key="same-key-across-bills",
                    invoice_id=invoice.pk, user=None, membership=object(),
                )
                with self.assertRaisesRegex(ValidationError, "different supplier payment"):
                    record_supplier_payment(
                        po=self.po, amount=Decimal("100"), method=SupplierPaymentMethod.BANK,
                        reference="ref", idempotency_key="same-key-across-bills",
                        invoice_id=another.pk, user=None, membership=object(),
                    )
                posting.assert_called_once()


    def test_manager_can_link_old_payment_without_another_cash_posting(self):
        from apps.accounts.models import Membership, MembershipRole, User
        from apps.purchasing.services import (
            record_supplier_payment, link_existing_supplier_payment_to_invoice,
        )
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services_exposure import supplier_invoice_settlement_rows

        invoice, _ = self.record(reference="MATCH-OLDER", amount=Decimal("1500"))
        manager = User.objects.create_user(email="po-link-manager@example.test", password="Password123!")
        membership = Membership.objects.create(
            tenant=self.tenant, user=manager, role=MembershipRole.OWNER,
        )
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense") as expense:
                payment, _ = record_supplier_payment(
                    po=self.po, amount=Decimal("500"), method=SupplierPaymentMethod.BANK,
                    reference="BANK-9988", idempotency_key="historical-match",
                    user=manager, membership=membership,
                )
                linked, replay = link_existing_supplier_payment_to_invoice(
                    po=self.po, payment_id=payment.pk, invoice_id=invoice.pk,
                    note="Matched bank statement reference BANK-9988 to supplier invoice.",
                    user=manager, membership=membership,
                )
                again, repeated = link_existing_supplier_payment_to_invoice(
                    po=self.po, payment_id=payment.pk, invoice_id=invoice.pk,
                    note="Repeated read of previously verified allocation.",
                    user=manager, membership=membership,
                )
                self.assertFalse(replay)
                self.assertTrue(repeated)
                self.assertEqual(again.pk, linked.pk)
                expense.assert_called_once()
        payment.refresh_from_db()
        self.assertEqual(payment.invoice_id, invoice.pk)
        self.assertEqual(payment.amount, Decimal("500"))
        rows, unallocated = supplier_invoice_settlement_rows(po=self.po)
        self.assertEqual(unallocated, Decimal("0"))
        self.assertEqual(rows[0]["unpaid"], Decimal("1000"))
        self.assertTrue(rows[0]["is_exact"])

    def test_manager_link_rejects_wrong_invoice_and_oversized_payment(self):
        from apps.accounts.models import Membership, MembershipRole, User
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services import (
            record_supplier_payment, link_existing_supplier_payment_to_invoice,
        )

        invoice, _ = self.record(reference="SMALL-BILL", amount=Decimal("400"))
        self.record(reference="BIG-BILL", amount=Decimal("1000"))
        manager = User.objects.create_user(email="po-link-reviewer@example.test", password="Password123!")
        membership = Membership.objects.create(
            tenant=self.tenant, user=manager, role=MembershipRole.OWNER,
        )
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense"):
                payment, _ = record_supplier_payment(
                    po=self.po, amount=Decimal("700"), method=SupplierPaymentMethod.CASH,
                    reference="old-700", idempotency_key="old-700",
                    user=manager, membership=membership,
                )
            with self.assertRaisesRegex(ValidationError, "exceeds"):
                link_existing_supplier_payment_to_invoice(
                    po=self.po, payment_id=payment.pk, invoice_id=invoice.pk,
                    note="Do not assign seven hundred to four hundred.",
                    user=manager, membership=membership,
                )
        payment.refresh_from_db()
        self.assertIsNone(payment.invoice_id)
        self.assertEqual(payment.amount, Decimal("700"))

    def test_storekeeper_cannot_allocate_supplier_payments(self):
        from apps.accounts.models import Membership, MembershipRole, User
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services import (
            record_supplier_payment, link_existing_supplier_payment_to_invoice,
        )

        invoice, _ = self.record(reference="MANAGER-ONLY", amount=Decimal("1000"))
        owner = User.objects.create_user(email="po-link-owner@example.test", password="Password123!")
        owner_membership = Membership.objects.create(
            tenant=self.tenant, user=owner, role=MembershipRole.OWNER,
        )
        warehouse = User.objects.create_user(email="po-link-storekeeper@example.test", password="Password123!")
        warehouse_membership = Membership.objects.create(
            tenant=self.tenant, user=warehouse, role=MembershipRole.STOREKEEPER,
        )
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense"):
                payment, _ = record_supplier_payment(
                    po=self.po, amount=Decimal("100"), method=SupplierPaymentMethod.BANK,
                    reference="guard-payment", idempotency_key="guard-payment",
                    user=owner, membership=owner_membership,
                )
            with self.assertRaisesRegex(ValidationError, "purchasing manager"):
                link_existing_supplier_payment_to_invoice(
                    po=self.po, payment_id=payment.pk, invoice_id=invoice.pk,
                    note="Warehouse staff cannot allocate financial history.",
                    user=warehouse, membership=warehouse_membership,
                )
        payment.refresh_from_db()
        self.assertIsNone(payment.invoice_id)


    def test_three_way_matching_uses_actual_receipt_quantity_cost_and_exact_total(self):
        from apps.purchasing.models import SupplierInvoiceLine
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            invoice, replay = record_supplier_invoice(
                po=self.po, reference="MATCH-PO-01", amount=Decimal("1500"),
                invoice_date=date(2026, 10, 1), due_date=date(2026, 10, 30),
                lines=[{"line_id": self.po.lines.get().pk, "quantity": "1.5", "unit_cost": "1000.00"}],
                user=None, membership=object(),
            )
            self.assertFalse(replay)
            matched = SupplierInvoiceLine.objects.get(invoice=invoice)
            self.assertEqual((matched.quantity, matched.unit_cost, matched.amount),
                             (Decimal("1.5"), Decimal("1000"), Decimal("1500")))
            with self.assertRaisesRegex(ValidationError, "exceeds accepted"):
                record_supplier_invoice(
                    po=self.po, reference="OVER-QTY", amount=Decimal("1000"),
                    invoice_date=date(2026, 10, 2), due_date=date(2026, 10, 30),
                    lines=[{"line_id": self.po.lines.get().pk, "quantity": "1", "unit_cost": "1000"}],
                    user=None, membership=object(),
                )
            with self.assertRaisesRegex(ValidationError, "differs"):
                record_supplier_invoice(
                    po=self.po, reference="PRICE-CHANGED", amount=Decimal("500"),
                    invoice_date=date(2026, 10, 2), due_date=date(2026, 10, 30),
                    lines=[{"line_id": self.po.lines.get().pk, "quantity": "0.5", "unit_cost": "999.99"}],
                    user=None, membership=object(),
                )
            with self.assertRaisesRegex(ValidationError, "does not equal"):
                record_supplier_invoice(
                    po=self.po, reference="WRONG-TOTAL", amount=Decimal("450"),
                    invoice_date=date(2026, 10, 2), due_date=date(2026, 10, 30),
                    lines=[{"line_id": self.po.lines.get().pk, "quantity": "0.5", "unit_cost": "1000"}],
                    user=None, membership=object(),
                )
            again, replay = record_supplier_invoice(
                po=self.po, reference="MATCH-PO-01", amount=Decimal("1500"),
                invoice_date=date(2026, 10, 1), due_date=date(2026, 10, 30),
                lines=[{"line_id": self.po.lines.get().pk, "quantity": "1.5", "unit_cost": "1000.00"}],
                user=None, membership=object(),
            )
            self.assertTrue(replay)
            self.assertEqual(again.pk, invoice.pk)

    def test_returned_goods_are_removed_once_without_supplier_refund_or_credit(self):
        from apps.accounts.models import Membership, MembershipRole, User
        from apps.inventory.models import StockBalance, StockMovement
        from apps.purchasing.models import PurchaseReceipt, PurchaseReceiptLine, SupplierReturn
        from apps.purchasing.services import return_received_goods_to_supplier, received_goods_value

        user = User.objects.create_user(email="return-manager@example.test", password="Password123!")
        membership = Membership.objects.create(
            tenant=self.tenant, user=user, role=MembershipRole.OWNER,
        )
        receipt = PurchaseReceipt.objects.create(
            tenant=self.tenant, purchase_order=self.po, delivery_reference="R-01",
        )
        accepted = PurchaseReceiptLine.objects.create(
            receipt=receipt, purchase_order_line=self.po.lines.get(),
            quantity_received=Decimal("2"),
        )
        stock = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.po.lines.get().menu_item,
            quantity=Decimal("2"),
        )
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            result, replay = return_received_goods_to_supplier(
                po=self.po, receipt_line_id=accepted.pk, quantity="1",
                reference="RETURN-01", note="Supplier accepted damaged sealed goods.",
                membership=membership, user=user,
            )
            second, repeated = return_received_goods_to_supplier(
                po=self.po, receipt_line_id=accepted.pk, quantity="1",
                reference="RETURN-01", note="Supplier accepted damaged sealed goods.",
                membership=membership, user=user,
            )
        self.assertFalse(replay)
        self.assertTrue(repeated)
        self.assertEqual(second.pk, result.pk)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, Decimal("1"))
        self.assertEqual(result.movement.quantity_change, Decimal("-1"))
        self.assertEqual(StockMovement.objects.filter(purchase_order=self.po).count(), 1)
        self.assertEqual(SupplierReturn.objects.filter(purchase_order=self.po).count(), 1)
        self.assertFalse(self.po.credits.exists())
        self.assertFalse(self.po.payments.exists())
        self.assertEqual(received_goods_value(self.po), Decimal("1000"))
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with self.assertRaises(ValidationError):
                return_received_goods_to_supplier(
                    po=self.po, receipt_line_id=accepted.pk, quantity="2",
                    reference="RETURN-02", note="More goods than are left in receipt.",
                    membership=membership, user=user,
                )

    def test_return_preserves_original_batch_and_rejects_wrong_lot(self):
        from apps.accounts.models import Membership, MembershipRole, User
        from apps.inventory.batches import InventoryBatch
        from apps.inventory.models import StockBalance, StockBatchAllocation
        from apps.purchasing.models import PurchaseReceipt, PurchaseReceiptLine
        from apps.purchasing.services import return_received_goods_to_supplier
        user = User.objects.create_user(email="batch-return-manager@example.test", password="Password123!")
        membership = Membership.objects.create(tenant=self.tenant, user=user, role=MembershipRole.OWNER)
        receipt = PurchaseReceipt.objects.create(tenant=self.tenant, purchase_order=self.po)
        batch = InventoryBatch.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.po.lines.get().menu_item,
            batch_code="RETURN-LOT-1", received_at=date(2026, 10, 1),
            expiry_date=date(2026, 12, 31), received_quantity=Decimal("2"),
            remaining_quantity=Decimal("1"),
        )
        accepted = PurchaseReceiptLine.objects.create(
            receipt=receipt, purchase_order_line=self.po.lines.get(),
            quantity_received=Decimal("2"), inventory_batch=batch,
        )
        stock = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=self.po.lines.get().menu_item,
            quantity=Decimal("2"),
        )
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with self.assertRaisesRegex(ValidationError, "originally received lot"):
                return_received_goods_to_supplier(
                    po=self.po, receipt_line_id=accepted.pk, quantity="2",
                    reference="LOT-FAIL", note="Returning two but only one in this lot.",
                    membership=membership, user=user,
                )
            ret, replay = return_received_goods_to_supplier(
                po=self.po, receipt_line_id=accepted.pk, quantity="1",
                reference="LOT-OK", note="Verified original damaged lot return.",
                membership=membership, user=user,
            )
        self.assertFalse(replay)
        batch.refresh_from_db()
        stock.refresh_from_db()
        self.assertEqual(batch.remaining_quantity, Decimal("0"))
        self.assertEqual(stock.quantity, Decimal("1"))
        self.assertEqual(StockBatchAllocation.objects.get(stock_movement=ret.movement).batch_id, batch.pk)
