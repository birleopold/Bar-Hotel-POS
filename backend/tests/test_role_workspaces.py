from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole
from apps.lodging.models import Reservation, ReservationStatus
from apps.pos.models import Order
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_SITE_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class RoleWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Workspaces", slug="role-workspaces")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Hotel")
        cls.other_site = Site.objects.create(tenant=cls.tenant, name="Other branch")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Bar", outlet_type=OutletType.BAR)
        cls.other_outlet = Outlet.objects.create(site=cls.other_site, name="Other bar", outlet_type=OutletType.BAR)
        cls.server = get_user_model().objects.create_user(email="workspace-server@test.local", password="Password9!")
        cls.reception = get_user_model().objects.create_user(email="workspace-reception@test.local", password="Password9!")
        cls.other_worker = get_user_model().objects.create_user(email="workspace-other@test.local", password="Password9!")
        membership = Membership.objects.create(tenant=cls.tenant, user=cls.server, role=MembershipRole.SERVER)
        membership.outlets.add(cls.outlet)
        membership = Membership.objects.create(tenant=cls.tenant, user=cls.reception, role=MembershipRole.FRONT_DESK)
        membership.sites.add(cls.site)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_SITE_KEY] = str(self.site.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_floor_actions_create_only_on_post_and_scope_my_orders(self):
        self.login(self.server)
        response = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(response.status_code, 200)
        actions = response.context["staff_dashboard_primary_actions"]
        self.assertIn("My orders", [a.label for a in actions])
        new = next(a for a in actions if a.label == "New order")
        self.assertEqual(new.method, "post")
        before = Order.objects.count()
        self.client.get(new.url)
        self.assertEqual(Order.objects.count(), before)
        self.client.post(new.url)
        own = Order.objects.get(created_by=self.server)
        other = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.other_worker)
        hidden = Order.objects.create(tenant=self.tenant, outlet=self.other_outlet, created_by=self.server)
        response = self.client.get(reverse("staff-orders"), {"mine": "1", "status": "open"})
        self.assertEqual(list(response.context["orders"]), [own])
        self.assertNotIn(other, response.context["orders"])
        self.assertNotIn(hidden, response.context["orders"])
        self.assertContains(response, 'name="mine" value="1"')

    def test_reception_lanes_filter_status_dates_and_branch(self):
        self.login(self.reception)
        today = timezone.localdate()
        def stay(name, start, end, status, site=None):
            return Reservation.objects.create(tenant=self.tenant, site=site or self.site, guest_name=name, check_in=start, check_out=end, status=status)
        arrival = stay("Expected", today, today + timedelta(days=2), ReservationStatus.CONFIRMED)
        stay("Cancelled", today, today + timedelta(days=1), ReservationStatus.CANCELLED)
        stay("Tomorrow", today + timedelta(days=1), today + timedelta(days=2), ReservationStatus.CONFIRMED)
        stay("Other branch", today, today + timedelta(days=1), ReservationStatus.CONFIRMED, self.other_site)
        departure = stay("Due today", today - timedelta(days=2), today, ReservationStatus.CHECKED_IN)
        overdue = stay("Overdue", today - timedelta(days=3), today - timedelta(days=1), ReservationStatus.CHECKED_IN)
        in_house = stay("Staying", today, today + timedelta(days=2), ReservationStatus.CHECKED_IN)
        route = reverse("staff-lodging-reservations")
        for lane, expected in [("arrivals", {arrival}), ("departures", {departure, overdue}), ("in_house", {departure, overdue, in_house})]:
            response = self.client.get(route, {"lane": lane})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.context["reservations"]), expected)
        response = self.client.get(route, {"lane": "arrivals", "status": "cancelled"})
        self.assertContains(response, "No stays match this task")
        self.assertNotContains(response, "Create your first reservation")
        response = self.client.get(reverse("staff-dashboard"))
        self.assertEqual([a.label for a in response.context["staff_dashboard_primary_actions"]], ["Arrivals", "Departures", "In-house", "Rooms", "New reservation"])
        self.assertNotContains(response, 'action="' + reverse("staff-order-quick-create") + '"')

    def test_retail_workspace_checkout_returns_and_lock(self):
        retail = Outlet.objects.create(site=self.site, name="Shop", outlet_type=OutletType.RETAIL)
        Membership.objects.get(user=self.server).outlets.add(retail)
        self.login(self.server)
        session = self.client.session
        session[STAFF_SESSION_OUTLET_KEY] = str(retail.pk)
        session.save()
        response = self.client.get(reverse("staff-dashboard"))
        self.assertContains(response, "Checkout workspace")
        actions = response.context["staff_dashboard_primary_actions"]
        self.assertEqual([a.label for a in actions], ["Checkout", "Active orders", "Returns", "Register", "Lock"])
        self.assertEqual(actions[0].method, "post")
        closed = Order.objects.create(tenant=self.tenant, outlet=retail, created_by=self.server, status="closed")
        Order.objects.create(tenant=self.tenant, outlet=retail, status="open")
        response = self.client.get(actions[2].url)
        self.assertEqual(list(response.context["orders"]), [closed])
        self.assertContains(response, "Refunds require an authorized manager")
        self.assertContains(response, 'name="task" value="returns"')
        response = self.client.post(actions[4].url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_storekeeper_receiving_queue_preserves_scope_and_partial_orders(self):
        from apps.purchasing.models import PurchaseOrder, PurchaseOrderStatus, Supplier
        user = get_user_model().objects.create_user(email="workspace-stock@test.local", password="Password9!")
        membership = Membership.objects.create(tenant=self.tenant, user=user, role=MembershipRole.STOREKEEPER)
        membership.outlets.add(self.outlet)
        membership.sites.add(self.site)
        supplier = Supplier.objects.create(tenant=self.tenant, name="Supplier")
        def po(status, outlet=None):
            return PurchaseOrder.objects.create(tenant=self.tenant, outlet=outlet or self.outlet, supplier=supplier, status=status)
        sent = po(PurchaseOrderStatus.SENT)
        partial = po(PurchaseOrderStatus.PARTIALLY_RECEIVED)
        po(PurchaseOrderStatus.DRAFT)
        po(PurchaseOrderStatus.RECEIVED)
        hidden = po(PurchaseOrderStatus.SENT, self.other_outlet)
        self.login(user)
        response = self.client.get(reverse("staff-dashboard"))
        actions = response.context["staff_dashboard_primary_actions"]
        self.assertEqual([a.label for a in actions], ["Receive", "Transfers", "Counts", "Low stock", "Purchase orders"])
        for action in actions:
            self.assertEqual(self.client.get(action.url).status_code, 200)
        response = self.client.get(actions[0].url)
        self.assertEqual(set(response.context["purchase_orders"]), {sent, partial})
        self.assertNotIn(hidden, response.context["purchase_orders"])
        self.assertContains(response, "Receive delivery")
        response = self.client.get(reverse("staff-purchasing-orders"), {"lane": "receiving", "status": "partially_received"})
        self.assertEqual(list(response.context["purchase_orders"]), [partial])
        self.assertContains(response, 'name="lane" value="receiving"')

    def test_supplemental_actions_respect_modules_and_read_only_role(self):
        from apps.staff.services.dashboard_actions import staff_dashboard_actions
        from apps.staff.services.modules import StaffNavVisibility, staff_nav_visibility
        membership = Membership.objects.get(user=self.server)
        vis = StaffNavVisibility(inventory=True, purchasing=True, lodging=True, events=True, finance=True, workspace=True)
        primary, secondary = staff_dashboard_actions(membership=membership, vis=vis, modules=frozenset(), show_lodging_nav=False, show_ops_nav=False)
        self.assertFalse(primary)
        self.assertFalse(secondary)
        membership.role = MembershipRole.ACCOUNTANT
        modules = frozenset({"inventory", "purchasing", "lodging", "events", "finance", "workspace", "pos"})
        vis = staff_nav_visibility(membership, modules)
        primary, secondary = staff_dashboard_actions(membership=membership, vis=vis, modules=modules, show_lodging_nav=True, show_ops_nav=True)
        for action in primary + secondary:
            self.assertNotIn("create", action.url)
            self.assertNotIn("/new/", action.url)
            self.assertEqual(action.method, "get")
        self.assertTrue(secondary)  # Overflow view links remain available.

    def test_storekeeper_can_transfer_and_count_only_assigned_stock(self):
        from apps.catalog.models import MenuCategory, MenuItem
        from apps.inventory.models import StockBalance, StockCountSession, StockMovement

        user = get_user_model().objects.create_user(email="stock-writes@test.local", password="Password9!")
        membership = Membership.objects.create(tenant=self.tenant, user=user, role=MembershipRole.STOREKEEPER)
        destination = Outlet.objects.create(site=self.site, name="Kitchen", outlet_type=OutletType.RESTAURANT)
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet, destination)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Ingredients")
        item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Rice", unit_price=1, track_inventory=True)
        StockBalance.objects.create(tenant=self.tenant, outlet=self.outlet, menu_item=item, quantity=10)
        self.login(user)
        transfer = {"from_outlet": str(self.outlet.pk), "to_outlet": str(destination.pk),
                    "menu_item": str(item.pk), "quantity": "2", "note": "Kitchen replenishment"}
        response = self.client.post(reverse("staff-inventory-transfer"), transfer)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockBalance.objects.get(outlet=self.outlet, menu_item=item).quantity, Decimal("8"))
        self.assertEqual(StockBalance.objects.get(outlet=destination, menu_item=item).quantity, Decimal("2"))
        movements = StockMovement.objects.count()
        response = self.client.post(reverse("staff-inventory-transfer"), {**transfer, "to_outlet": str(self.other_outlet.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(StockMovement.objects.count(), movements)

        response = self.client.post(reverse("staff-inventory-count-create"), {"outlet": str(self.outlet.pk), "note": "Daily count"})
        self.assertEqual(response.status_code, 302)
        count = StockCountSession.objects.get(created_by=user)
        detail = reverse("staff-inventory-count-detail", kwargs={"session_id": count.pk})
        response = self.client.post(detail, {"action": "submit", f"counted_{item.pk}": "7"})
        self.assertEqual(response.status_code, 302)
        count.refresh_from_db()
        self.assertEqual(count.status, "review")
        self.assertEqual(StockBalance.objects.get(outlet=self.outlet, menu_item=item).quantity, Decimal("8"))
        self.assertEqual(StockMovement.objects.count(), movements)
        manager_user = get_user_model().objects.create_user(
            email="stock-approver@test.local", password="Password9!",
        )
        manager_membership = Membership.objects.create(
            tenant=self.tenant, user=manager_user, role=MembershipRole.SITE_MANAGER,
        )
        manager_membership.sites.add(self.site)
        manager_membership.outlets.add(self.outlet)
        self.login(manager_user)
        response = self.client.post(detail, {"action": "approve"})
        self.assertEqual(response.status_code, 302)
        count.refresh_from_db()
        self.assertEqual(count.status, "completed")
        self.assertEqual(count.approved_by_id, manager_user.pk)
        self.assertEqual(StockBalance.objects.get(outlet=self.outlet, menu_item=item).quantity, Decimal("7"))
        self.login(user)
        hidden = StockCountSession.objects.create(tenant=self.tenant, outlet=self.other_outlet, created_by=user)
        self.assertEqual(self.client.post(reverse("staff-inventory-count-detail", kwargs={"session_id": hidden.pk}), {"action": "cancel"}).status_code, 404)

        membership.role = MembershipRole.ACCOUNTANT
        membership.save(update_fields=["role"])
        before = StockMovement.objects.count()
        self.assertEqual(self.client.post(reverse("staff-inventory-transfer"), transfer).status_code, 302)
        self.assertEqual(StockMovement.objects.count(), before)

    def test_storekeeper_receives_goods_without_purchase_finance_permissions(self):
        from apps.catalog.models import MenuCategory, MenuItem
        from apps.inventory.models import StockBalance
        from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, Supplier

        user = get_user_model().objects.create_user(email="stock-receive@test.local", password="Password9!")
        membership = Membership.objects.create(tenant=self.tenant, user=user, role=MembershipRole.STOREKEEPER)
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet)
        supplier = Supplier.objects.create(tenant=self.tenant, name="Rice supplier")
        category = MenuCategory.objects.create(tenant=self.tenant, name="Dry goods")
        item = MenuItem.objects.create(tenant=self.tenant, category=category, name="Rice", unit_price=2, track_inventory=True)
        po = PurchaseOrder.objects.create(tenant=self.tenant, outlet=self.outlet, supplier=supplier, status="sent")
        line = PurchaseOrderLine.objects.create(purchase_order=po, menu_item=item, quantity_ordered=10, unit_cost=1)
        self.login(user)
        path = reverse("staff-purchasing-order-detail", kwargs={"po_id": po.pk})
        page = self.client.get(path)
        self.assertContains(page, 'value="receive"')
        self.assertNotContains(page, 'value="supplier_payment"')
        self.assertNotContains(page, 'value="cancel"')
        response = self.client.post(path, {"action": "receive", f"recv_{line.pk}": "3", "delivery_reference": "DEL-1"})
        self.assertEqual(response.status_code, 302)
        line.refresh_from_db()
        self.assertEqual(line.quantity_received, Decimal("3"))
        self.assertEqual(StockBalance.objects.get(outlet=self.outlet, menu_item=item).quantity, Decimal("3"))
        self.client.post(path, {"action": "cancel"})
        po.refresh_from_db()
        self.assertEqual(po.status, "partially_received")
