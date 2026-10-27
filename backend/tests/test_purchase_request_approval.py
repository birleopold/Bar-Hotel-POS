from datetime import date, timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import AuditEvent
from apps.catalog.models import MenuCategory, MenuItem
from apps.purchasing.models import (
    PurchaseApprovalStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
    Supplier,
)
from apps.purchasing.serializers import PurchaseOrderStatusUpdateSerializer
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class PurchaseRequestApprovalTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Purchase approval", slug="purchase-approval")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["purchasing", "inventory"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Stock room",
            outlet_type=OutletType.SUPERMARKET,
        )
        category = MenuCategory.objects.create(tenant=self.tenant, name="General")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=category,
            name="Soap",
            sku="SOAP-REQ",
            unit_price=Decimal("4000"),
            track_inventory=True,
        )
        self.supplier = Supplier.objects.create(
            tenant=self.tenant,
            name="Soap supplier",
        )
        self.storekeeper = User.objects.create_user(
            email="requester@test.local",
            password="Password9!",
        )
        self.manager = User.objects.create_user(
            email="manager@test.local",
            password="Password9!",
        )
        self.store_member = Membership.objects.create(
            tenant=self.tenant,
            user=self.storekeeper,
            role=MembershipRole.STOREKEEPER,
        )
        self.manager_member = Membership.objects.create(
            tenant=self.tenant,
            user=self.manager,
            role=MembershipRole.OUTLET_MANAGER,
        )
        for member in (self.store_member, self.manager_member):
            member.sites.add(self.site)
            member.outlets.add(self.outlet)

    def _client_for(self, user):
        client = Client()
        self.assertTrue(client.login(username=user.email, password="Password9!"))
        session = client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        return client

    def _create_request(
        self,
        *,
        user=None,
        reference="REQ-001",
        needed_by=None,
        request_reason="Low stock before weekend demand",
    ):
        client = self._client_for(user or self.storekeeper)
        response = client.post(
            reverse("staff-purchasing-order-create"),
            {
                "supplier": str(self.supplier.pk),
                "outlet": str(self.outlet.pk),
                "reference": reference,
                "expected_date": "",
                "needed_by": needed_by.isoformat() if needed_by else "",
                "request_reason": request_reason,
                "notes": "Replenish shelf stock",
                "line_0_menu_item": str(self.item.pk),
                "line_0_quantity_ordered": "8",
                "line_0_product_package": "",
                "line_0_package_count": "",
                "line_0_cartons": "",
                "line_0_unit_cost": "2500",
            },
        )
        self.assertEqual(response.status_code, 302)
        return client, PurchaseOrder.objects.get(reference=reference)

    def test_request_context_is_preserved_visible_and_audited_on_approval(self):
        needed = date.today() + timedelta(days=5)
        _client, po = self._create_request(
            reference="REQ-CONTEXT",
            needed_by=needed,
            request_reason="Promotion starts next week",
        )
        self.assertEqual(po.needed_by, needed)
        self.assertEqual(po.request_reason, "Promotion starts next week")

        manager = self._client_for(self.manager)
        detail_url = reverse(
            "staff-purchasing-order-detail",
            kwargs={"po_id": po.pk},
        )
        page = manager.get(detail_url)
        self.assertContains(page, needed.isoformat())
        self.assertContains(page, "Promotion starts next week")

        approved = manager.post(
            detail_url,
            {
                "action": "approve_request",
                "review_note": "Approved for promotion stock",
            },
        )
        self.assertEqual(approved.status_code, 302)
        event = AuditEvent.objects.filter(
            tenant=self.tenant,
            action="purchasing.request_approved",
            entity_id=str(po.pk),
        ).latest("created_at")
        self.assertEqual(event.payload["needed_by"], needed.isoformat())
        self.assertEqual(
            event.payload["request_reason"],
            "Promotion starts next week",
        )

    def test_approval_lane_prioritizes_earliest_needed_date_then_undated(self):
        today = date.today()
        self._create_request(
            reference="REQ-LATE",
            needed_by=today + timedelta(days=10),
        )
        self._create_request(
            reference="REQ-EARLY",
            needed_by=today + timedelta(days=2),
        )
        self._create_request(
            reference="REQ-NODATE",
            needed_by=None,
        )
        manager = self._client_for(self.manager)
        page = manager.get(
            reverse("staff-purchasing-orders"),
            {"lane": "approval"},
        )
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertLess(body.index("REQ-EARLY"), body.index("REQ-LATE"))
        self.assertLess(body.index("REQ-LATE"), body.index("REQ-NODATE"))

    def test_storekeeper_creates_pending_request_and_cannot_send_it(self):
        client, po = self._create_request()
        self.assertEqual(po.status, PurchaseOrderStatus.DRAFT)
        self.assertEqual(po.approval_status, PurchaseApprovalStatus.PENDING)
        self.assertEqual(po.created_by, self.storekeeper)
        self.assertIsNone(po.reviewed_by)

        serializer = PurchaseOrderStatusUpdateSerializer(
            po,
            data={"status": PurchaseOrderStatus.SENT},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("manager-approved", str(serializer.errors))

        detail = client.get(
            reverse("staff-purchasing-order-detail", kwargs={"po_id": po.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Pending approval")
        self.assertContains(detail, "Withdraw my request")
        self.assertNotContains(detail, "Mark order as sent")

    def test_manager_approval_queue_approve_then_send(self):
        _client, po = self._create_request(reference="REQ-APPROVE")
        manager = self._client_for(self.manager)

        queue = manager.get(
            reverse("staff-purchasing-orders"),
            {"lane": "approval"},
        )
        self.assertEqual(queue.status_code, 200)
        self.assertContains(queue, "REQ-APPROVE")
        self.assertContains(queue, "Pending approval")

        detail_url = reverse(
            "staff-purchasing-order-detail",
            kwargs={"po_id": po.pk},
        )
        approved = manager.post(
            detail_url,
            {
                "action": "approve_request",
                "review_note": "Needed for normal weekly replenishment",
            },
        )
        self.assertEqual(approved.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.approval_status, PurchaseApprovalStatus.APPROVED)
        self.assertEqual(po.reviewed_by, self.manager)
        self.assertIsNotNone(po.reviewed_at)

        sent = manager.post(detail_url, {"action": "send"})
        self.assertEqual(sent.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrderStatus.SENT)

    def test_rejection_requires_reason_and_rejected_request_cannot_send(self):
        _client, po = self._create_request(reference="REQ-REJECT")
        manager = self._client_for(self.manager)
        detail_url = reverse(
            "staff-purchasing-order-detail",
            kwargs={"po_id": po.pk},
        )

        no_reason = manager.post(
            detail_url,
            {"action": "reject_request", "review_note": ""},
        )
        self.assertEqual(no_reason.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.approval_status, PurchaseApprovalStatus.PENDING)

        rejected = manager.post(
            detail_url,
            {
                "action": "reject_request",
                "review_note": "Supplier quote is too high; request a new quote.",
            },
        )
        self.assertEqual(rejected.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.approval_status, PurchaseApprovalStatus.REJECTED)
        self.assertIn("too high", po.review_note)

        serializer = PurchaseOrderStatusUpdateSerializer(
            po,
            data={"status": PurchaseOrderStatus.SENT},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())

    def test_manager_created_po_is_approved_without_extra_click(self):
        _client, po = self._create_request(
            user=self.manager,
            reference="MANAGER-DRAFT",
        )
        self.assertEqual(po.status, PurchaseOrderStatus.DRAFT)
        self.assertEqual(po.approval_status, PurchaseApprovalStatus.APPROVED)
        self.assertEqual(po.reviewed_by, self.manager)
        self.assertIsNotNone(po.reviewed_at)

    def test_requester_can_withdraw_pending_request(self):
        client, po = self._create_request(reference="REQ-WITHDRAW")
        response = client.post(
            reverse(
                "staff-purchasing-order-detail",
                kwargs={"po_id": po.pk},
            ),
            {"action": "withdraw_request"},
        )
        self.assertEqual(response.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrderStatus.CANCELLED)
        self.assertEqual(po.approval_status, PurchaseApprovalStatus.PENDING)
        self.assertEqual(po.reviewed_by, self.storekeeper)

    def test_manager_cannot_approve_own_pending_request(self):
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            outlet=self.outlet,
            created_by=self.manager,
            status=PurchaseOrderStatus.DRAFT,
            approval_status=PurchaseApprovalStatus.PENDING,
        )
        manager = self._client_for(self.manager)
        response = manager.post(
            reverse(
                "staff-purchasing-order-detail",
                kwargs={"po_id": po.pk},
            ),
            {
                "action": "approve_request",
                "review_note": "Self approval attempt",
            },
        )
        self.assertEqual(response.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.approval_status, PurchaseApprovalStatus.PENDING)
