from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import AuditEvent
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.costing import reconcile_incomplete_cost_basis
from apps.inventory.models import StockBalance
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class InventoryCostReconciliationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Legacy Cost Reconciliation",
            slug="legacy-cost-reconciliation",
        )
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["inventory", "purchasing", "pos"],
            default_currency="UGX",
            retail_min_margin_percent=Decimal("20"),
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Stock room",
            outlet_type=OutletType.SUPERMARKET,
        )
        category = MenuCategory.objects.create(
            tenant=self.tenant,
            name="General",
        )
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=category,
            name="Legacy soap",
            sku="LEGACY-SOAP",
            unit_price=Decimal("4000"),
            track_inventory=True,
        )
        self.balance = StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.item,
            quantity=Decimal("12"),
            average_unit_cost=None,
            cost_basis_complete=False,
        )
        self.manager = User.objects.create_user(
            email="cost-manager@test.local",
            password="Password9!",
        )
        self.storekeeper = User.objects.create_user(
            email="cost-store@test.local",
            password="Password9!",
        )
        self.manager_member = Membership.objects.create(
            tenant=self.tenant,
            user=self.manager,
            role=MembershipRole.OUTLET_MANAGER,
        )
        self.store_member = Membership.objects.create(
            tenant=self.tenant,
            user=self.storekeeper,
            role=MembershipRole.STOREKEEPER,
        )
        for member in (self.manager_member, self.store_member):
            member.sites.add(self.site)
            member.outlets.add(self.outlet)

    def _client(self, user):
        client = Client()
        self.assertTrue(client.login(username=user.email, password="Password9!"))
        session = client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        return client

    def test_reconciliation_sets_trusted_cost_without_changing_quantity(self):
        changed = reconcile_incomplete_cost_basis(
            tenant_id=self.tenant.pk,
            outlet=self.outlet,
            menu_item=self.item,
            unit_cost="1750.1250",
            reason="Opening stock verified against supplier invoice 4471",
            user=self.manager,
        )
        self.assertEqual(changed.quantity, Decimal("12"))
        self.assertEqual(changed.average_unit_cost, Decimal("1750.1250"))
        self.assertTrue(changed.cost_basis_complete)

        event = AuditEvent.objects.get(
            tenant=self.tenant,
            action="inventory.cost_basis_reconciled",
            entity_id=str(self.balance.pk),
        )
        self.assertFalse(event.payload["quantity_changed"])
        self.assertFalse(event.payload["historical_sales_rewritten"])
        self.assertEqual(event.payload["before"]["quantity"], "12.000")
        self.assertEqual(event.payload["after"]["average_unit_cost"], "1750.1250")

    def test_reconciliation_refuses_to_overwrite_trusted_cost(self):
        self.balance.average_unit_cost = Decimal("1800")
        self.balance.cost_basis_complete = True
        self.balance.save(
            update_fields=["average_unit_cost", "cost_basis_complete", "updated_at"]
        )
        with self.assertRaises(ValidationError):
            reconcile_incomplete_cost_basis(
                tenant_id=self.tenant.pk,
                outlet=self.outlet,
                menu_item=self.item,
                unit_cost="1500",
                reason="Trying to overwrite a trusted basis",
                user=self.manager,
            )
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.average_unit_cost, Decimal("1800.0000"))
        self.assertTrue(self.balance.cost_basis_complete)

    def test_reconciliation_requires_positive_stock_and_evidence_reason(self):
        self.balance.quantity = Decimal("0")
        self.balance.save(update_fields=["quantity", "updated_at"])
        with self.assertRaises(ValidationError):
            reconcile_incomplete_cost_basis(
                tenant_id=self.tenant.pk,
                outlet=self.outlet,
                menu_item=self.item,
                unit_cost="1750",
                reason="Supplier invoice 4471",
                user=self.manager,
            )
        self.balance.quantity = Decimal("12")
        self.balance.save(update_fields=["quantity", "updated_at"])
        with self.assertRaises(ValidationError):
            reconcile_incomplete_cost_basis(
                tenant_id=self.tenant.pk,
                outlet=self.outlet,
                menu_item=self.item,
                unit_cost="1750",
                reason="guess",
                user=self.manager,
            )

    def test_manager_can_reconcile_from_stock_screen_storekeeper_cannot(self):
        manager = self._client(self.manager)
        page = manager.get(reverse("staff-inventory-balances"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Reconcile cost")

        response = manager.post(
            reverse("staff-inventory-balances"),
            {
                "action": "reconcile_cost",
                "balance_id": str(self.balance.pk),
                "unit_cost": "1750",
                "reason": "Verified opening balance supplier invoice",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.balance.refresh_from_db()
        self.assertTrue(self.balance.cost_basis_complete)
        self.assertEqual(self.balance.quantity, Decimal("12"))

        self.balance.average_unit_cost = None
        self.balance.cost_basis_complete = False
        self.balance.save(
            update_fields=["average_unit_cost", "cost_basis_complete", "updated_at"]
        )
        storekeeper = self._client(self.storekeeper)
        page = storekeeper.get(reverse("staff-inventory-balances"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Reconcile cost")
        denied = storekeeper.post(
            reverse("staff-inventory-balances"),
            {
                "action": "reconcile_cost",
                "balance_id": str(self.balance.pk),
                "unit_cost": "1000",
                "reason": "Unauthorized reconciliation attempt",
            },
        )
        self.assertEqual(denied.status_code, 302)
        self.balance.refresh_from_db()
        self.assertFalse(self.balance.cost_basis_complete)
        self.assertIsNone(self.balance.average_unit_cost)
