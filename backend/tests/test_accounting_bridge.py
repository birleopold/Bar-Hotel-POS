from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.finance.accounting_bridge import (
    build_accounting_preview,
    create_accounting_export,
)
from apps.finance.models import (
    AccountingExportBatch,
    AccountingMapping,
    AccountingMappingKind,
)
from apps.lodging.models import Folio, FolioLine, FolioPayment
from apps.pos.models import Order, OrderLine, OrderStatus, Payment, Refund
from apps.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierInvoice,
    SupplierInvoiceLine,
    SupplierPayment,
)
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_KEY,
    STAFF_SESSION_SITE_KEY,
    STAFF_SESSION_TENANT_KEY,
)
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class AccountingBridgeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Accounting Bridge",
            slug="accounting-bridge-tests",
        )
        TenantSettings.objects.update_or_create(
            tenant=self.tenant,
            defaults={
                "business_lines": ["supermarket"],
                "default_currency": "UGX",
                "enabled_staff_modules": ["pos", "sales", "inventory", "finance"],
            },
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Shop",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.other_site = Site.objects.create(tenant=self.tenant, name="Other")
        self.other_outlet = Outlet.objects.create(
            site=self.other_site,
            name="Hidden shop",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.owner = User.objects.create_user(
            email="accounting-owner@test.local",
            password="Password9!",
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.owner,
            role=MembershipRole.OWNER,
        )
        self.accountant = User.objects.create_user(
            email="accounting-accountant@test.local",
            password="Password9!",
        )
        self.accountant_membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.accountant,
            role=MembershipRole.ACCOUNTANT,
        )
        self.accountant_membership.sites.add(self.site)
        self.accountant_membership.outlets.add(self.outlet)

        self.category = MenuCategory.objects.create(
            tenant=self.tenant,
            name="Soap",
        )
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Bar soap",
            unit_price=Decimal("100.00"),
            track_inventory=True,
        )

    def _mapping(self, kind, code, name, *, source_key="", source_label=""):
        return AccountingMapping.objects.create(
            tenant=self.tenant,
            kind=kind,
            source_key=source_key,
            source_label=source_label,
            account_code=code,
            account_name=name,
            created_by=self.owner,
        )

    def _complete_mappings(self):
        self._mapping(
            AccountingMappingKind.REVENUE_DEFAULT,
            "4000",
            "=Retail revenue",
        )
        self._mapping(AccountingMappingKind.RETURNS, "4090", "Sales returns")
        self._mapping(
            AccountingMappingKind.TENDER,
            "1010",
            "Cash clearing",
            source_key="cash",
            source_label="Cash",
        )
        self._mapping(
            AccountingMappingKind.TENDER,
            "1020",
            "Card clearing",
            source_key="card",
            source_label="Card",
        )
        self._mapping(
            AccountingMappingKind.TAX_LIABILITY,
            "2100",
            "VAT payable",
        )
        self._mapping(
            AccountingMappingKind.COGS_DEFAULT,
            "5000",
            "Cost of goods sold",
        )
        self._mapping(
            AccountingMappingKind.INVENTORY_DEFAULT,
            "1200",
            "Inventory asset",
        )

    def _sale(
        self,
        *,
        outlet=None,
        total=Decimal("110.00"),
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        trusted_cost=True,
        unknown_cost=False,
        cash=Decimal("60.00"),
        card=Decimal("50.00"),
    ):
        outlet = outlet or self.outlet
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=outlet,
            status=OrderStatus.CLOSED,
            is_paid=True,
            subtotal=subtotal,
            tax_total=tax,
            total=total,
            created_by=self.owner,
        )
        line = OrderLine.objects.create(
            order=order,
            menu_item=self.item,
            label=self.item.name,
            quantity=Decimal("1"),
            unit_price=subtotal,
            line_total=subtotal,
            tax_amount=tax,
            inventory_tracked_snapshot=True,
            cost_unit_snapshot=(Decimal("60.00") if trusted_cost and not unknown_cost else None),
            cost_basis_complete_snapshot=(trusted_cost and not unknown_cost),
            merchandise_category_snapshot=self.category.name,
        )
        if cash:
            Payment.objects.create(
                tenant=self.tenant,
                order=order,
                amount=cash,
                method="cash",
                idempotency_key=f"cash-{order.pk}",
                recorded_by=self.owner,
            )
        if card:
            Payment.objects.create(
                tenant=self.tenant,
                order=order,
                amount=card,
                method="card",
                idempotency_key=f"card-{order.pk}",
                recorded_by=self.owner,
            )
        return order, line

    def _login(self, user, *, site=None, outlet=None):
        client = Client()
        self.assertTrue(client.login(username=user.email, password="Password9!"))
        session = client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_SITE_KEY] = str((site or self.site).pk)
        session[STAFF_SESSION_OUTLET_KEY] = str((outlet or self.outlet).pk)
        session.save()
        return client

    def test_balanced_sale_tax_tender_cogs_and_refund_preview(self):
        self._complete_mappings()
        order, line = self._sale()
        card_payment = order.payments.get(method="card")
        Refund.objects.create(
            tenant=self.tenant,
            order=order,
            payment=card_payment,
            amount=Decimal("22.00"),
            reason="Customer return",
            idempotency_key="accounting-refund",
            recorded_by=self.owner,
        )

        today = timezone.localdate()
        preview = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertTrue(preview["ready"])
        self.assertTrue(preview["balanced"])
        self.assertEqual(preview["total_debit"], Decimal("192.00"))
        self.assertEqual(preview["total_credit"], Decimal("192.00"))
        self.assertEqual(preview["missing_mappings"], [])
        self.assertEqual(preview["source_summary"]["completed_sales"], 1)
        self.assertEqual(preview["source_summary"]["refunds"], 1)
        self.assertEqual(preview["source_summary"]["trusted_cost_lines"], 1)

        by_code = {}
        for row in preview["journal_lines"]:
            by_code.setdefault(row["account_code"], []).append(row)
        self.assertEqual(
            sum(Decimal(row["credit"]) for row in by_code["4000"]),
            Decimal("100.00"),
        )
        self.assertEqual(
            sum(Decimal(row["credit"]) - Decimal(row["debit"]) for row in by_code["2100"]),
            Decimal("8.00"),
        )
        self.assertEqual(
            sum(Decimal(row["debit"]) for row in by_code["5000"]),
            Decimal("60.00"),
        )
        self.assertEqual(
            sum(Decimal(row["credit"]) for row in by_code["1200"]),
            Decimal("60.00"),
        )
        self.assertEqual(
            sum(Decimal(row["debit"]) for row in by_code["4090"]),
            Decimal("20.00"),
        )

    def test_missing_mapping_fails_closed_and_unknown_cost_is_explicit(self):
        self._mapping(
            AccountingMappingKind.REVENUE_DEFAULT,
            "4000",
            "Revenue",
        )
        self._mapping(
            AccountingMappingKind.TENDER,
            "1010",
            "Cash",
            source_key="cash",
            source_label="Cash",
        )
        self._mapping(
            AccountingMappingKind.TAX_LIABILITY,
            "2100",
            "VAT",
        )
        self._sale(
            trusted_cost=False,
            unknown_cost=True,
            cash=Decimal("60.00"),
            card=Decimal("50.00"),
        )
        today = timezone.localdate()
        preview = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertFalse(preview["ready"])
        self.assertIn("Tender clearing mapping for card", preview["missing_mappings"])
        self.assertEqual(preview["source_summary"]["unknown_cost_lines"], 1)
        self.assertTrue(
            any("no COGS/inventory journal was guessed" in item for item in preview["warnings"])
        )
        self.assertFalse(any(row["account_code"] in {"5000", "1200"} for row in preview["journal_lines"]))

    def test_folio_receivable_and_payment_journal_balance(self):
        self._complete_mappings()
        self._mapping(
            AccountingMappingKind.ACCOUNTS_RECEIVABLE,
            "1300",
            "Guest receivables",
        )
        folio = Folio.objects.create(
            tenant=self.tenant,
            site=self.site,
            guest_name="Guest A",
            currency="UGX",
        )
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            folio=folio,
            status=OrderStatus.CLOSED,
            is_paid=False,
            subtotal=Decimal("100.00"),
            tax_total=Decimal("10.00"),
            total=Decimal("110.00"),
            created_by=self.owner,
        )
        OrderLine.objects.create(
            order=order,
            menu_item=self.item,
            label=self.item.name,
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
            tax_amount=Decimal("10.00"),
            inventory_tracked_snapshot=True,
            cost_unit_snapshot=Decimal("60.00"),
            cost_basis_complete_snapshot=True,
            merchandise_category_snapshot=self.category.name,
        )
        Payment.objects.create(
            tenant=self.tenant,
            order=order,
            amount=Decimal("30.00"),
            method="cash",
            idempotency_key="folio-pos-partial",
            recorded_by=self.owner,
        )
        FolioLine.objects.create(
            tenant=self.tenant,
            folio=folio,
            description=f"POS {order.bill_reference}",
            amount=Decimal("100.00"),
            tax_amount=Decimal("10.00"),
            source_order=order,
        )
        FolioLine.objects.create(
            tenant=self.tenant,
            folio=folio,
            description=f"Paid at POS {order.bill_reference}",
            amount=Decimal("-30.00"),
            source_order=order,
        )
        FolioPayment.objects.create(
            tenant=self.tenant,
            folio=folio,
            amount=Decimal("80.00"),
            method="card",
            idempotency_key="folio-balance-payment",
            recorded_by=self.owner,
        )

        today = timezone.localdate()
        preview = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertTrue(preview["ready"])
        self.assertTrue(preview["balanced"])
        self.assertEqual(preview["source_summary"]["folio_charges"], 1)
        self.assertEqual(preview["source_summary"]["folio_payments"], 1)
        self.assertEqual(preview["total_debit"], Decimal("250.00"))
        self.assertEqual(preview["total_credit"], Decimal("250.00"))
        ar_rows = [
            row for row in preview["journal_lines"]
            if row["account_code"] == "1300"
        ]
        self.assertEqual(
            sum(Decimal(row["debit"]) for row in ar_rows),
            Decimal("80.00"),
        )
        self.assertEqual(
            sum(Decimal(row["credit"]) for row in ar_rows),
            Decimal("80.00"),
        )

    def test_supplier_payable_invoice_and_payment_are_balanced(self):
        self._mapping(
            AccountingMappingKind.INVENTORY_DEFAULT,
            "1200",
            "Inventory asset",
        )
        self._mapping(
            AccountingMappingKind.ACCOUNTS_PAYABLE,
            "2200",
            "Supplier payables",
        )
        self._mapping(
            AccountingMappingKind.TENDER,
            "1030",
            "Bank clearing",
            source_key="bank",
            source_label="Bank transfer",
        )
        supplier = Supplier.objects.create(
            tenant=self.tenant,
            name="Soap Supplier",
        )
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=supplier,
            outlet=self.outlet,
            status="received",
            reference="PO-AP-1",
            created_by=self.owner,
        )
        po_line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            menu_item=self.item,
            quantity_ordered=Decimal("1"),
            quantity_received=Decimal("1"),
            unit_cost=Decimal("60.00"),
        )
        today = timezone.localdate()
        invoice = SupplierInvoice.objects.create(
            tenant=self.tenant,
            purchase_order=po,
            reference="INV-AP-1",
            invoice_date=today,
            due_date=today,
            amount=Decimal("60.00"),
            recorded_by=self.owner,
        )
        SupplierInvoiceLine.objects.create(
            invoice=invoice,
            purchase_order_line=po_line,
            quantity=Decimal("1"),
            unit_cost=Decimal("60.00"),
            amount=Decimal("60.00"),
        )
        SupplierPayment.objects.create(
            tenant=self.tenant,
            purchase_order=po,
            invoice=invoice,
            amount=Decimal("60.00"),
            method="bank",
            reference="BANK-1",
            idempotency_key="supplier-ap-payment",
            recorded_by=self.owner,
        )

        preview = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertTrue(preview["ready"])
        self.assertEqual(preview["source_summary"]["supplier_invoices"], 1)
        self.assertEqual(preview["source_summary"]["supplier_payments"], 1)
        self.assertEqual(preview["total_debit"], Decimal("120.00"))
        self.assertEqual(preview["total_credit"], Decimal("120.00"))
        ap_rows = [
            row for row in preview["journal_lines"]
            if row["account_code"] == "2200"
        ]
        self.assertEqual(
            sum(Decimal(row["credit"]) for row in ap_rows),
            Decimal("60.00"),
        )
        self.assertEqual(
            sum(Decimal(row["debit"]) for row in ap_rows),
            Decimal("60.00"),
        )

    def test_unmatched_supplier_invoice_blocks_export(self):
        self._mapping(
            AccountingMappingKind.INVENTORY_DEFAULT,
            "1200",
            "Inventory asset",
        )
        self._mapping(
            AccountingMappingKind.ACCOUNTS_PAYABLE,
            "2200",
            "Supplier payables",
        )
        supplier = Supplier.objects.create(
            tenant=self.tenant,
            name="Mismatch Supplier",
        )
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=supplier,
            outlet=self.outlet,
            status="received",
            reference="PO-MISMATCH",
            created_by=self.owner,
        )
        po_line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            menu_item=self.item,
            quantity_ordered=Decimal("1"),
            quantity_received=Decimal("1"),
            unit_cost=Decimal("60.00"),
        )
        today = timezone.localdate()
        invoice = SupplierInvoice.objects.create(
            tenant=self.tenant,
            purchase_order=po,
            reference="INV-MISMATCH",
            invoice_date=today,
            due_date=today,
            amount=Decimal("70.00"),
            recorded_by=self.owner,
        )
        SupplierInvoiceLine.objects.create(
            invoice=invoice,
            purchase_order_line=po_line,
            quantity=Decimal("1"),
            unit_cost=Decimal("60.00"),
            amount=Decimal("60.00"),
        )
        preview = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertFalse(preview["ready"])
        self.assertEqual(
            preview["source_summary"]["unmatched_supplier_invoices"],
            1,
        )
        self.assertTrue(
            any("INV-MISMATCH" in item for item in preview["validation_errors"])
        )

    def test_export_is_idempotent_and_mapping_change_does_not_mutate_history(self):
        self._complete_mappings()
        self._sale()
        today = timezone.localdate()
        preview = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        first, replay = create_accounting_export(
            tenant_id=self.tenant.pk,
            preview=preview,
            allowed_outlet_ids=[self.outlet.pk],
            user=self.owner,
        )
        self.assertFalse(replay)
        again, replay = create_accounting_export(
            tenant_id=self.tenant.pk,
            preview=preview,
            allowed_outlet_ids=[self.outlet.pk],
            user=self.owner,
        )
        self.assertTrue(replay)
        self.assertEqual(first.pk, again.pk)
        original_lines = list(first.journal_lines)
        original_mapping = dict(first.mapping_snapshot)

        revenue = AccountingMapping.objects.get(
            tenant=self.tenant,
            kind=AccountingMappingKind.REVENUE_DEFAULT,
            source_key="",
        )
        revenue.account_code = "4010"
        revenue.account_name = "Changed revenue"
        revenue.save(update_fields=["account_code", "account_name", "updated_at"])

        changed = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        second, replay = create_accounting_export(
            tenant_id=self.tenant.pk,
            preview=changed,
            allowed_outlet_ids=[self.outlet.pk],
            user=self.owner,
        )
        self.assertFalse(replay)
        self.assertNotEqual(first.pk, second.pk)
        first.refresh_from_db()
        self.assertEqual(first.journal_lines, original_lines)
        self.assertEqual(first.mapping_snapshot, original_mapping)
        self.assertTrue(any(row["account_code"] == "4010" for row in second.journal_lines))

    def test_accounting_ui_scope_csv_safety_and_historical_download_guard(self):
        self._complete_mappings()
        self._sale()
        hidden_order, _ = self._sale(outlet=self.other_outlet)

        today = timezone.localdate()
        preview = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        visible_batch, _ = create_accounting_export(
            tenant_id=self.tenant.pk,
            preview=preview,
            allowed_outlet_ids=[self.outlet.pk],
            user=self.owner,
        )
        hidden_preview = build_accounting_preview(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.other_outlet.pk],
            currency="UGX",
        )
        hidden_batch, _ = create_accounting_export(
            tenant_id=self.tenant.pk,
            preview=hidden_preview,
            allowed_outlet_ids=[self.other_outlet.pk],
            user=self.owner,
        )

        client = self._login(self.accountant)
        page = client.get(
            reverse("staff-accounting-export"),
            {"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Ready and balanced")
        self.assertContains(page, self.outlet.name)
        self.assertNotContains(page, self.other_outlet.name)

        csv_response = client.get(
            reverse(
                "staff-accounting-export-download",
                kwargs={"batch_id": visible_batch.pk},
            )
        )
        self.assertEqual(csv_response.status_code, 200)
        body = csv_response.content.decode()
        self.assertIn("'=Retail revenue", body)
        self.assertIn("account_code,account_name", body)
        self.assertEqual(
            client.get(
                reverse(
                    "staff-accounting-export-download",
                    kwargs={"batch_id": hidden_batch.pk},
                )
            ).status_code,
            404,
        )

    def test_mapping_form_is_tenant_scoped(self):
        foreign = Tenant.objects.create(name="Foreign", slug="accounting-foreign")
        TenantSettings.objects.update_or_create(
            tenant=foreign,
            defaults={"business_lines": ["supermarket"]},
        )
        foreign_category = MenuCategory.objects.create(
            tenant=foreign,
            name="Private category",
        )
        client = self._login(self.owner)
        response = client.post(
            reverse("staff-workspace-accounting-mapping-create"),
            {
                "kind": AccountingMappingKind.REVENUE_CATEGORY,
                "category": str(foreign_category.pk),
                "tender_method": "",
                "account_code": "4999",
                "account_name": "Private",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(
            AccountingMapping.objects.filter(
                tenant=self.tenant,
                account_code="4999",
            ).exists()
        )
