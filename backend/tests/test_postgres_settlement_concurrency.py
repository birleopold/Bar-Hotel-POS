"""Run with a disposable PostgreSQL test database to exercise real row locks."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.finance.models import CashbookEntry, FinanceCategoryKind
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, SupplierPayment, Supplier
from apps.purchasing.services import receive_purchase_order_goods, record_supplier_payment
from apps.pos.models import PosShift, PosShiftStatus
from apps.pos.services import open_pos_shift
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class SupplierSettlementConcurrencyTests(TransactionTestCase):
    def test_simultaneous_payments_cannot_exceed_received_value(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks are required")
        tenant = Tenant.objects.create(name="Concurrency", slug="supplier-concurrency")
        site = Site.objects.create(tenant=tenant, name="Main")
        outlet = Outlet.objects.create(site=site, name="Store", outlet_type=OutletType.SUPERMARKET)
        user = User.objects.create_user(email="concurrency@test.local", password="TestPass9!")
        membership = Membership.objects.create(tenant=tenant, user=user, role=MembershipRole.OWNER)
        supplier = Supplier.objects.create(tenant=tenant, name="Supplier")
        category = MenuCategory.objects.create(tenant=tenant, name="Goods")
        item = MenuItem.objects.create(tenant=tenant, category=category, name="Box", unit_price=Decimal("10"), track_inventory=True)
        po = PurchaseOrder.objects.create(tenant=tenant, supplier=supplier, outlet=outlet, status=PurchaseOrderStatus.SENT, created_by=user)
        line = PurchaseOrderLine.objects.create(purchase_order=po, menu_item=item, quantity_ordered=Decimal("1"), unit_cost=Decimal("10"))
        receive_purchase_order_goods(po=po, lines_payload=[{"line_id": line.id, "quantity": Decimal("1")}], user=user, membership=membership)
        start = Barrier(2, timeout=10)

        def pay(number):
            close_old_connections()
            try:
                start.wait()
                try:
                    record_supplier_payment(
                        po=PurchaseOrder.objects.get(pk=po.pk), amount=Decimal("10"),
                        method="cash", reference=f"R{number}", idempotency_key=f"concurrent-{number}",
                        user=User.objects.get(pk=user.pk), membership=Membership.objects.get(pk=membership.pk),
                    )
                    return "paid"
                except ValidationError:
                    return "rejected"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(pay, (1, 2)))
        self.assertCountEqual(outcomes, ["paid", "rejected"])
        self.assertEqual(SupplierPayment.objects.filter(purchase_order=po).count(), 1)
        self.assertEqual(CashbookEntry.objects.filter(tenant=tenant, category__kind=FinanceCategoryKind.EXPENSE).count(), 1)


class RegisterOpenConcurrencyTests(TransactionTestCase):
    def test_simultaneous_open_requests_create_one_shift(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks are required")
        tenant = Tenant.objects.create(name="Register race", slug="register-race")
        site = Site.objects.create(tenant=tenant, name="Main")
        outlet = Outlet.objects.create(site=site, name="Counter", outlet_type=OutletType.RETAIL)
        user = User.objects.create_user(email="register-race@test.local", password="TestPass9!")
        start = Barrier(2, timeout=10)

        def open_register():
            close_old_connections()
            try:
                start.wait()
                try:
                    open_pos_shift(
                        tenant_id=tenant.id, outlet=Outlet.objects.get(pk=outlet.pk),
                        user=User.objects.get(pk=user.pk), opening_cash=Decimal("20"),
                    )
                    return "opened"
                except ValidationError:
                    return "rejected"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(open_register) for _ in range(2)]
            outcomes = [future.result() for future in futures]
        self.assertCountEqual(outcomes, ["opened", "rejected"])
        self.assertEqual(PosShift.objects.filter(outlet=outlet, status=PosShiftStatus.OPEN).count(), 1)
