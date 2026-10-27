from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, RetailAssemblyComponent
from apps.inventory.models import StockBalance
from apps.inventory.services import execute_retail_assembly
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class RetailAssemblyCostingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Assembly Costing",
            slug="assembly-costing",
        )
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["inventory", "pos"],
            default_currency="UGX",
            retail_min_margin_percent=Decimal("20"),
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Stock room",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(
            email="assembly-cost@test.local",
            password="Password9!",
        )
        self.membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=MembershipRole.OWNER,
        )
        self.membership.sites.add(self.site)
        self.membership.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(
            tenant=self.tenant,
            name="Bundles",
        )
        self.box = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Gift box",
            sku="GIFT-BOX",
            unit_price=Decimal("6000"),
            track_inventory=True,
        )
        self.soap = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Soap",
            sku="SOAP-COMP",
            unit_price=Decimal("2000"),
            track_inventory=True,
        )
        self.towel = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Towel",
            sku="TOWEL-COMP",
            unit_price=Decimal("3000"),
            track_inventory=True,
        )
        RetailAssemblyComponent.objects.create(
            tenant=self.tenant,
            parent_item=self.box,
            component_item=self.soap,
            quantity_per_unit=Decimal("2"),
        )
        RetailAssemblyComponent.objects.create(
            tenant=self.tenant,
            parent_item=self.box,
            component_item=self.towel,
            quantity_per_unit=Decimal("1"),
        )

    def _balance(self, item, qty, cost=None, complete=False):
        return StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=item,
            quantity=Decimal(str(qty)),
            average_unit_cost=Decimal(str(cost)) if cost is not None else None,
            cost_basis_complete=complete,
        )

    def test_build_rolls_trusted_component_cost_into_finished_weighted_average(self):
        self._balance(self.soap, "20", "1000", True)
        self._balance(self.towel, "10", "500", True)
        self._balance(self.box, "1", "3000", True)

        run = execute_retail_assembly(
            tenant_id=self.tenant.pk,
            outlet=self.outlet,
            assembled_item=self.box,
            quantity="2",
            direction="build",
            user=self.user,
            membership=self.membership,
            note="Gift-pack build",
        )

        self.assertTrue(run.cost_basis_complete_snapshot)
        self.assertEqual(run.finished_unit_cost_snapshot, Decimal("2500.0000"))
        self.assertEqual(
            run.component_cost_snapshot[str(self.soap.pk)]["unit_cost"],
            "1000.0000",
        )
        self.assertEqual(
            run.component_cost_snapshot[str(self.towel.pk)]["unit_cost"],
            "500.0000",
        )

        soap = StockBalance.objects.get(outlet=self.outlet, menu_item=self.soap)
        towel = StockBalance.objects.get(outlet=self.outlet, menu_item=self.towel)
        finished = StockBalance.objects.get(outlet=self.outlet, menu_item=self.box)
        self.assertEqual(soap.quantity, Decimal("16"))
        self.assertEqual(towel.quantity, Decimal("8"))
        self.assertEqual(finished.quantity, Decimal("3"))
        self.assertTrue(finished.cost_basis_complete)
        self.assertEqual(finished.average_unit_cost, Decimal("2666.6667"))

    def test_untrusted_component_keeps_built_finished_stock_cost_incomplete(self):
        self._balance(self.soap, "20", "1000", True)
        self._balance(self.towel, "10", None, False)
        self._balance(self.box, "0", None, False)

        run = execute_retail_assembly(
            tenant_id=self.tenant.pk,
            outlet=self.outlet,
            assembled_item=self.box,
            quantity="2",
            direction="build",
            user=self.user,
            membership=self.membership,
        )

        self.assertFalse(run.cost_basis_complete_snapshot)
        self.assertIsNone(run.finished_unit_cost_snapshot)
        self.assertIsNone(
            run.component_cost_snapshot[str(self.towel.pk)]["unit_cost"]
        )
        finished = StockBalance.objects.get(outlet=self.outlet, menu_item=self.box)
        self.assertEqual(finished.quantity, Decimal("2"))
        self.assertFalse(finished.cost_basis_complete)
        self.assertIsNone(finished.average_unit_cost)

    def test_unbuild_remains_conservative_and_invalidates_component_cost_trust(self):
        self._balance(self.soap, "10", "1000", True)
        self._balance(self.towel, "5", "500", True)
        self._balance(self.box, "2", "2500", True)

        run = execute_retail_assembly(
            tenant_id=self.tenant.pk,
            outlet=self.outlet,
            assembled_item=self.box,
            quantity="1",
            direction="unbuild",
            user=self.user,
            membership=self.membership,
        )
        self.assertFalse(run.cost_basis_complete_snapshot)
        self.assertIsNone(run.finished_unit_cost_snapshot)

        soap = StockBalance.objects.get(outlet=self.outlet, menu_item=self.soap)
        towel = StockBalance.objects.get(outlet=self.outlet, menu_item=self.towel)
        finished = StockBalance.objects.get(outlet=self.outlet, menu_item=self.box)
        self.assertEqual(finished.quantity, Decimal("1"))
        self.assertEqual(finished.average_unit_cost, Decimal("2500.0000"))
        self.assertTrue(finished.cost_basis_complete)
        self.assertFalse(soap.cost_basis_complete)
        self.assertIsNone(soap.average_unit_cost)
        self.assertFalse(towel.cost_basis_complete)
        self.assertIsNone(towel.average_unit_cost)
