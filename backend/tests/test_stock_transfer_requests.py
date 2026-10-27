from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import (
    StockBalance,
    StockMovement,
    StockTransferReceipt,
    StockTransferRequest,
    StockTransferRequestStatus,
)
from apps.inventory.services import verify_stock_transfer_receipt
from apps.inventory.transfer_requests import (
    create_stock_transfer_request,
    review_stock_transfer_request,
)
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class StockTransferRequestTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Transfer Requests",
            slug="transfer-requests",
        )
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["inventory", "pos"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.source = Outlet.objects.create(
            site=self.site,
            name="Warehouse",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.destination = Outlet.objects.create(
            site=self.site,
            name="Retail floor",
            outlet_type=OutletType.SUPERMARKET,
        )
        category = MenuCategory.objects.create(
            tenant=self.tenant,
            name="General",
        )
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=category,
            name="Cooking oil",
            sku="REQ-OIL",
            unit_price=Decimal("5000"),
            track_inventory=True,
        )
        StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.source,
            menu_item=self.item,
            quantity=Decimal("10"),
            average_unit_cost=Decimal("1200"),
            cost_basis_complete=True,
        )

        self.requester = User.objects.create_user(
            email="requester-transfer@test.local",
            password="Password9!",
        )
        self.manager = User.objects.create_user(
            email="manager-transfer@test.local",
            password="Password9!",
        )
        self.receiver = User.objects.create_user(
            email="receiver-transfer@test.local",
            password="Password9!",
        )

        self.requester_membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.requester,
            role=MembershipRole.STOREKEEPER,
        )
        self.requester_membership.sites.add(self.site)
        self.requester_membership.outlets.add(self.destination)

        self.manager_membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.manager,
            role=MembershipRole.OUTLET_MANAGER,
        )
        self.manager_membership.sites.add(self.site)
        self.manager_membership.outlets.add(self.source)

        self.receiver_membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.receiver,
            role=MembershipRole.STOREKEEPER,
        )
        self.receiver_membership.sites.add(self.site)
        self.receiver_membership.outlets.add(self.destination)

    def _client(self, user, outlet):
        client = Client()
        self.assertTrue(
            client.login(username=user.email, password="Password9!")
        )
        session = client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(outlet.pk)
        session.save()
        return client

    def test_request_approval_dispatch_receive_moves_stock_only_at_correct_stage(self):
        requester = self._client(self.requester, self.destination)
        page = requester.get(reverse("staff-inventory-transfer"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Request stock from another section")
        self.assertContains(page, "Warehouse")
        self.assertContains(page, "Retail floor")

        created = requester.post(
            reverse("staff-inventory-transfer"),
            {
                "from_outlet": str(self.source.pk),
                "to_outlet": str(self.destination.pk),
                "menu_item": str(self.item.pk),
                "quantity": "4",
                "cartons": "",
                "needed_by": "",
                "note": "Shelf stock is below the weekend requirement",
            },
        )
        self.assertEqual(created.status_code, 302)
        request_row = StockTransferRequest.objects.get()
        self.assertEqual(
            request_row.status, StockTransferRequestStatus.PENDING
        )
        self.assertEqual(request_row.requested_quantity, Decimal("4"))
        self.assertEqual(
            StockBalance.objects.get(
                outlet=self.source, menu_item=self.item
            ).quantity,
            Decimal("10"),
        )
        self.assertFalse(StockTransferReceipt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

        manager = self._client(self.manager, self.source)
        queue = manager.get(reverse("staff-inventory-transfer-requests"))
        self.assertEqual(queue.status_code, 200)
        self.assertContains(queue, "Cooking oil")
        self.assertContains(queue, "Approve")

        approved = manager.post(
            reverse("staff-inventory-transfer-requests"),
            {
                "request_id": str(request_row.pk),
                "action": "approve",
                "approved_quantity": "3",
                "review_note": "Three units available for this request",
            },
        )
        self.assertEqual(approved.status_code, 302)
        request_row.refresh_from_db()
        self.assertEqual(
            request_row.status, StockTransferRequestStatus.APPROVED
        )
        self.assertEqual(request_row.approved_quantity, Decimal("3"))
        self.assertEqual(
            StockBalance.objects.get(
                outlet=self.source, menu_item=self.item
            ).quantity,
            Decimal("10"),
        )
        self.assertFalse(StockTransferReceipt.objects.exists())

        dispatched = manager.post(
            reverse("staff-inventory-transfer-requests"),
            {
                "request_id": str(request_row.pk),
                "action": "dispatch",
            },
        )
        self.assertEqual(dispatched.status_code, 302)
        request_row.refresh_from_db()
        self.assertEqual(
            request_row.status, StockTransferRequestStatus.DISPATCHED
        )
        receipt = request_row.transfer_receipt
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.status, "in_transit")
        self.assertEqual(receipt.dispatched_quantity, Decimal("3"))
        self.assertEqual(
            StockBalance.objects.get(
                outlet=self.source, menu_item=self.item
            ).quantity,
            Decimal("7"),
        )
        self.assertFalse(
            StockBalance.objects.filter(
                outlet=self.destination,
                menu_item=self.item,
            ).exists()
        )
        self.assertEqual(
            StockMovement.objects.filter(
                transfer_batch=receipt.transfer_batch
            ).count(),
            1,
        )

        verify_stock_transfer_receipt(
            receipt=receipt,
            membership=self.receiver_membership,
            user=self.receiver,
            received_quantity="3",
        )
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "matched")
        destination = StockBalance.objects.get(
            outlet=self.destination,
            menu_item=self.item,
        )
        self.assertEqual(destination.quantity, Decimal("3"))
        self.assertEqual(destination.average_unit_cost, Decimal("1200.0000"))
        self.assertTrue(destination.cost_basis_complete)
        self.assertEqual(
            StockMovement.objects.filter(
                transfer_batch=receipt.transfer_batch
            ).count(),
            2,
        )

    def test_requester_cannot_self_approve_and_rejection_moves_no_stock(self):
        manager_requester = User.objects.create_user(
            email="manager-requester@test.local",
            password="Password9!",
        )
        both = Membership.objects.create(
            tenant=self.tenant,
            user=manager_requester,
            role=MembershipRole.OUTLET_MANAGER,
        )
        both.sites.add(self.site)
        both.outlets.add(self.source, self.destination)

        row = create_stock_transfer_request(
            tenant_id=self.tenant.pk,
            membership=both,
            from_outlet=self.source,
            to_outlet=self.destination,
            menu_item=self.item,
            quantity="2",
            user=manager_requester,
            note="Manager-originated transfer request",
        )
        with self.assertRaises(ValidationError):
            review_stock_transfer_request(
                transfer_request=row,
                membership=both,
                user=manager_requester,
                decision=StockTransferRequestStatus.APPROVED,
                approved_quantity="2",
            )

        review_stock_transfer_request(
            transfer_request=row,
            membership=self.manager_membership,
            user=self.manager,
            decision=StockTransferRequestStatus.REJECTED,
            note="Source stock is reserved for another branch",
        )
        row.refresh_from_db()
        self.assertEqual(row.status, StockTransferRequestStatus.REJECTED)
        self.assertIsNone(row.approved_quantity)
        self.assertEqual(
            StockBalance.objects.get(
                outlet=self.source, menu_item=self.item
            ).quantity,
            Decimal("10"),
        )
        self.assertFalse(StockTransferReceipt.objects.exists())

    def test_approval_cannot_exceed_request_or_source_stock(self):
        row = create_stock_transfer_request(
            tenant_id=self.tenant.pk,
            membership=self.requester_membership,
            from_outlet=self.source,
            to_outlet=self.destination,
            menu_item=self.item,
            quantity="4",
            user=self.requester,
        )
        with self.assertRaises(ValidationError):
            review_stock_transfer_request(
                transfer_request=row,
                membership=self.manager_membership,
                user=self.manager,
                decision=StockTransferRequestStatus.APPROVED,
                approved_quantity="5",
            )
        row.refresh_from_db()
        self.assertEqual(row.status, StockTransferRequestStatus.PENDING)

        StockBalance.objects.filter(
            outlet=self.source, menu_item=self.item
        ).update(quantity=Decimal("2"))
        with self.assertRaises(ValidationError):
            review_stock_transfer_request(
                transfer_request=row,
                membership=self.manager_membership,
                user=self.manager,
                decision=StockTransferRequestStatus.APPROVED,
                approved_quantity="3",
            )
        row.refresh_from_db()
        self.assertEqual(row.status, StockTransferRequestStatus.PENDING)
