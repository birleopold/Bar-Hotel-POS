from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, RetailAssemblyComponent
from apps.inventory.batches import InventoryBatch
from apps.inventory.models import RetailAssemblyRun, StockBalance, StockMovement, StockReason
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class RetailAssemblyJourneyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Retail assemblies", slug="retail-assemblies")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["inventory", "pos", "purchasing"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main store")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Stock room", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(
            email="assemblies@test.local", password="Password9!",
        )
        member = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OWNER,
        )
        member.sites.add(self.site)
        member.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Bundles")
        self.finished = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Gift pack",
            sku="GIFT-PACK",
            unit_price=Decimal("15000"),
            track_inventory=True,
        )
        self.component_a = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Soap",
            sku="SOAP",
            unit_price=Decimal("3000"),
            track_inventory=True,
        )
        self.component_b = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Lotion",
            sku="LOTION",
            unit_price=Decimal("5000"),
            track_inventory=True,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def _configure_bom(self):
        RetailAssemblyComponent.objects.create(
            tenant=self.tenant,
            parent_item=self.finished,
            component_item=self.component_a,
            quantity_per_unit=Decimal("2"),
        )
        RetailAssemblyComponent.objects.create(
            tenant=self.tenant,
            parent_item=self.finished,
            component_item=self.component_b,
            quantity_per_unit=Decimal("1"),
        )

    def _stock(self, item, qty):
        return StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=item,
            quantity=Decimal(str(qty)),
        )

    def test_owner_can_configure_assembly_bom_in_console(self):
        url = reverse("console-org-menu-item-assembly-create", args=[self.finished.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add assembly component")
        created = self.client.post(
            url,
            {
                "component_item": str(self.component_a.pk),
                "quantity_per_unit": "2",
            },
        )
        self.assertEqual(created.status_code, 302)
        line = RetailAssemblyComponent.objects.get(parent_item=self.finished)
        self.assertEqual(line.component_item, self.component_a)
        self.assertEqual(line.quantity_per_unit, Decimal("2"))

        listing = self.client.get(reverse("console-org-menu-item-assembly", args=[self.finished.pk]))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Retail assembly")
        self.assertContains(listing, "Soap")
        self.assertContains(listing, reverse("staff-inventory-assemblies"))

    def test_staff_build_and_unbuild_are_atomic_and_audited(self):
        self._configure_bom()
        self._stock(self.component_a, "20")
        self._stock(self.component_b, "10")
        self._stock(self.finished, "0")
        url = reverse("staff-inventory-assemblies")

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Build &amp; unbuild assemblies")
        self.assertContains(page, "Gift pack")

        built = self.client.post(
            url,
            {
                "outlet": str(self.outlet.pk),
                "assembled_item": str(self.finished.pk),
                "direction": "build",
                "quantity": "4",
                "note": "Morning gift-pack build",
            },
        )
        self.assertEqual(built.status_code, 302)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.finished).quantity,
            Decimal("4"),
        )
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.component_a).quantity,
            Decimal("12"),
        )
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.component_b).quantity,
            Decimal("6"),
        )
        build_run = RetailAssemblyRun.objects.get(direction="build")
        self.assertEqual(build_run.quantity, Decimal("4"))
        self.assertEqual(build_run.stock_movements.count(), 3)
        self.assertEqual(
            set(build_run.stock_movements.values_list("reason", flat=True)),
            {StockReason.ASSEMBLY_BUILD},
        )

        unbuilt = self.client.post(
            url,
            {
                "outlet": str(self.outlet.pk),
                "assembled_item": str(self.finished.pk),
                "direction": "unbuild",
                "quantity": "2",
                "note": "Opened two packs",
            },
        )
        self.assertEqual(unbuilt.status_code, 302)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.finished).quantity,
            Decimal("2"),
        )
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.component_a).quantity,
            Decimal("16"),
        )
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.component_b).quantity,
            Decimal("8"),
        )
        self.assertEqual(RetailAssemblyRun.objects.filter(direction="unbuild").count(), 1)

    def test_insufficient_component_rolls_back_every_balance_and_run(self):
        self._configure_bom()
        self._stock(self.component_a, "3")
        self._stock(self.component_b, "10")
        self._stock(self.finished, "0")
        response = self.client.post(
            reverse("staff-inventory-assemblies"),
            {
                "outlet": str(self.outlet.pk),
                "assembled_item": str(self.finished.pk),
                "direction": "build",
                "quantity": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockBalance.objects.get(menu_item=self.component_a).quantity, Decimal("3"))
        self.assertEqual(StockBalance.objects.get(menu_item=self.component_b).quantity, Decimal("10"))
        self.assertEqual(StockBalance.objects.get(menu_item=self.finished).quantity, Decimal("0"))
        self.assertFalse(RetailAssemblyRun.objects.exists())
        self.assertFalse(StockMovement.objects.filter(reason=StockReason.ASSEMBLY_BUILD).exists())

    def test_batch_tracked_component_blocks_assembly_without_side_effect(self):
        self._configure_bom()
        self._stock(self.component_a, "20")
        self._stock(self.component_b, "10")
        self._stock(self.finished, "0")
        InventoryBatch.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.component_a,
            batch_code="SOAP-LOT-1",
            received_at=date.today(),
            received_quantity=Decimal("20"),
            remaining_quantity=Decimal("20"),
        )
        response = self.client.post(
            reverse("staff-inventory-assemblies"),
            {
                "outlet": str(self.outlet.pk),
                "assembled_item": str(self.finished.pk),
                "direction": "build",
                "quantity": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockBalance.objects.get(menu_item=self.component_a).quantity, Decimal("20"))
        self.assertEqual(StockBalance.objects.get(menu_item=self.finished).quantity, Decimal("0"))
        self.assertFalse(RetailAssemblyRun.objects.exists())

    def test_assembly_route_rejects_foreign_outlet(self):
        self._configure_bom()
        other_tenant = Tenant.objects.create(name="Other assembly tenant", slug="other-assembly")
        other_site = Site.objects.create(tenant=other_tenant, name="Other")
        foreign_outlet = Outlet.objects.create(
            site=other_site, name="Foreign", outlet_type=OutletType.SUPERMARKET,
        )
        response = self.client.post(
            reverse("staff-inventory-assemblies"),
            {
                "outlet": str(foreign_outlet.pk),
                "assembled_item": str(self.finished.pk),
                "direction": "build",
                "quantity": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RetailAssemblyRun.objects.exists())
