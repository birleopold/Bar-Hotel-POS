from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import AuditEvent, ExceptionPolicy, ExceptionReview, SensitiveActionApproval
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance
from apps.lodging.models import Reservation
from apps.pos.models import Order, Payment, PosShift, Refund
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_SITE_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class ManagementWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Management", slug="management-tests")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Shop", outlet_type=OutletType.RETAIL)
        cls.other = Outlet.objects.create(site=cls.site, name="Other", outlet_type=OutletType.RETAIL)
        cls.foreign = Tenant.objects.create(name="Foreign", slug="management-foreign")
        site = Site.objects.create(tenant=cls.foreign, name="Foreign")
        cls.foreign_outlet = Outlet.objects.create(site=site, name="Foreign", outlet_type=OutletType.RETAIL)
        cls.owner = User.objects.create_user(email="management-owner@test.local", password="Password9!")
        cls.manager = User.objects.create_user(email="management-manager@test.local", password="Password9!")
        cls.worker = User.objects.create_user(email="management-worker@test.local", password="Password9!")
        Membership.objects.create(tenant=cls.tenant, user=cls.owner, role=MembershipRole.OWNER)
        for user, role in [(cls.manager, MembershipRole.OUTLET_MANAGER), (cls.worker, MembershipRole.SERVER)]:
            m = Membership.objects.create(tenant=cls.tenant, user=user, role=role)
            m.outlets.add(cls.outlet)
        cls.order = Order.objects.create(tenant=cls.tenant, outlet=cls.outlet, total=100, status="closed", currency="UGX")
        payment = Payment.objects.create(tenant=cls.tenant, order=cls.order, amount=100, idempotency_key="management-payment")
        cls.refund = Refund.objects.create(tenant=cls.tenant, order=cls.order, payment=payment, amount=20, reason="Return", idempotency_key="management-refund")
        cls.shift = PosShift.objects.create(tenant=cls.tenant, outlet=cls.outlet, status="closed", counted_cash=90, expected_cash=100, closed_at=timezone.now())
        category = MenuCategory.objects.create(tenant=cls.tenant, name="Stock")
        item = MenuItem.objects.create(tenant=cls.tenant, category=category, name="Test item", unit_price=10, track_inventory=True, reorder_level=5)
        cls.balance = StockBalance.objects.create(tenant=cls.tenant, outlet=cls.outlet, menu_item=item, quantity=2)
        cls.stay = Reservation.objects.create(tenant=cls.tenant, site=cls.site, guest_name="Overdue guest", status="checked_in", check_in=timezone.localdate()-timedelta(days=3), check_out=timezone.localdate()-timedelta(days=1))

    def login(self, user=None):
        self.client.force_login(user or self.owner)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session[STAFF_SESSION_SITE_KEY] = str(self.site.pk)
        session.save()

    def rows(self):
        return self.client.get(reverse("staff-management")).context["exception_rows"]

    def review_data(self, row, **changes):
        return {"kind": row.kind, "entity_id": row.entity_id, "fingerprint": row.fingerprint, "status": "reviewed", "note": "Checked with worker", **changes}

    def test_manager_destinations_and_role_guard(self):
        self.login(self.manager)
        response = self.client.get(reverse("staff-dashboard"))
        actions = response.context["staff_dashboard_primary_actions"]
        self.assertEqual([a.label for a in actions], ["Today", "Exceptions", "Approvals", "Team", "Reports"])
        for action in actions:
            self.assertEqual(self.client.get(action.url).status_code, 200)
        self.login(self.worker)
        self.assertEqual(self.client.get(reverse("staff-management")).status_code, 403)
        self.assertEqual(self.client.post(reverse("staff-management"), {}).status_code, 403)
        self.assertNotContains(self.client.get(reverse("staff-dashboard")), '?view=exceptions')

    def test_live_categories_scope_and_shift_source(self):
        self.login()
        hidden = PosShift.objects.create(tenant=self.tenant, outlet=self.other, status="closed", expected_cash=20, counted_cash=0, closed_at=timezone.now())
        foreign = PosShift.objects.create(tenant=self.foreign, outlet=self.foreign_outlet, status="closed", expected_cash=20, counted_cash=0, closed_at=timezone.now())
        rows = self.rows()
        self.assertEqual({r.kind for r in rows}, {"cash_variance", "refund", "low_stock", "overdue_departure"})
        self.assertNotIn(str(hidden.pk), {r.entity_id for r in rows})
        self.assertNotIn(str(foreign.pk), {r.entity_id for r in rows})
        shift = next(r for r in rows if r.kind == "cash_variance")
        response = self.client.get(shift.url)
        self.assertContains(response, "Register reconciliation")
        self.assertEqual(response.context["variance"], Decimal("-10"))
        for obj in [hidden, foreign]:
            self.assertEqual(self.client.get(reverse("staff-management-shift", args=[obj.pk])).status_code, 404)
        session = self.client.session
        session[STAFF_SESSION_OUTLET_KEY] = "__all__"
        session.save()
        self.assertIn(str(hidden.pk), {r.entity_id for r in self.rows()})
        self.assertEqual(self.client.get(shift.url).status_code, 200)

    def test_reviews_idempotency_reopen_history_and_no_posting(self):
        self.login(self.manager)
        row = next(r for r in self.rows() if r.kind == "cash_variance")
        data = self.review_data(row)
        route = reverse("staff-management")
        self.assertEqual(self.client.post(route, data).status_code, 302)
        self.client.post(route, data)
        self.assertEqual(ExceptionReview.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="exception.reviewed").count(), 1)
        self.client.post(route, {**data, "status": "open", "note": "Needs recount"})
        self.assertEqual(AuditEvent.objects.filter(action="exception.reviewed").count(), 2)
        current = next(r for r in self.rows() if r.kind == "cash_variance")
        self.assertEqual(current.review.status, "open")
        self.assertEqual(len(current.history), 2)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.counted_cash, Decimal("90"))
        self.assertEqual(Refund.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_changed_source_reappears_and_rejects_stale_assessment(self):
        self.login()
        row = next(r for r in self.rows() if r.kind == "low_stock")
        data = self.review_data(row)
        self.client.post(reverse("staff-management"), data)
        self.balance.quantity = 1
        self.balance.save()
        response = self.client.post(reverse("staff-management"), data)
        self.assertEqual(response.status_code, 409)
        current = next(r for r in self.rows() if r.kind == "low_stock")
        self.assertIsNone(current.review)
        self.assertEqual(len(current.history), 1)
        self.balance.quantity = 10
        self.balance.save()
        self.assertEqual(self.client.post(reverse("staff-management"), self.review_data(current)).status_code, 409)

    def test_policy_validation_thresholds_and_password_session_guard(self):
        self.login()
        route = reverse("staff-management")
        self.assertEqual(self.client.post(route, {"action": "policy", "cash_variance_threshold": "-1", "refund_threshold": "0", "lookback_days": 0}).status_code, 400)
        response = self.client.post(route, {"action": "policy", "cash_variance_threshold": "10", "refund_threshold": "21", "lookback_days": 30})
        self.assertEqual(response.status_code, 302)
        self.assertEqual({r.kind for r in self.rows()}, {"low_stock", "overdue_departure"})
        self.assertEqual(AuditEvent.objects.filter(action="exception.policy_updated").count(), 1)
        session = self.client.session
        session["staff_pin_authenticated"] = True
        session.save()
        self.assertEqual(self.client.post(route, {"action": "policy"}).status_code, 403)
        self.login(self.manager)
        self.assertEqual(self.client.post(route, {"action": "policy"}).status_code, 403)

    def test_modules_and_approval_team_scope(self):
        self.login(self.manager)
        hidden_worker = User.objects.create_user(email="hidden-worker@test.local", password="Password9!")
        m = Membership.objects.create(tenant=self.tenant, user=hidden_worker, role=MembershipRole.SERVER)
        m.outlets.add(self.other)
        hidden_order = Order.objects.create(tenant=self.tenant, outlet=self.other)
        response = self.client.get(reverse("staff-management"), {"view": "team"})
        self.assertNotContains(response, hidden_worker.email)
        self.assertContains(response, self.worker.email)
        response = self.client.get(reverse("staff-management"), {"view": "approvals"})
        self.assertEqual(list(response.context["approval_orders"]), [self.order])
        self.assertNotIn(hidden_order, response.context["approval_orders"])
        TenantSettings.objects.create(tenant=self.tenant, enabled_staff_modules=["workspace"])
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.client.get(reverse("staff-management-shift", args=[self.shift.pk])).status_code, 404)
        self.assertFalse(self.client.get(reverse("staff-management"), {"view": "approvals"}).context["approval_orders"])

    def test_manager_approval_evidence_is_outlet_scoped_and_redacted(self):
        requester = Membership.objects.get(tenant=self.tenant, user=self.worker)
        approver = Membership.objects.get(tenant=self.tenant, user=self.manager)
        visible = SensitiveActionApproval.objects.create(
            tenant=self.tenant,
            requester=requester,
            approver=approver,
            scope_outlet=self.outlet,
            action="refund",
            entity_type="order",
            entity_id=str(self.order.pk),
            request_key="management-visible-approval",
            intent_hash="a" * 64,
            intent_payload={"amount": "20.00", "reason": "Customer return"},
            expires_at=timezone.now() + timedelta(minutes=2),
            used_at=timezone.now(),
        )
        hidden_order = Order.objects.create(
            tenant=self.tenant, outlet=self.other, total=50, status="closed", currency="UGX",
        )
        SensitiveActionApproval.objects.create(
            tenant=self.tenant,
            requester=requester,
            approver=approver,
            scope_outlet=self.other,
            action="refund",
            entity_type="order",
            entity_id=str(hidden_order.pk),
            request_key="management-hidden-approval",
            intent_hash="b" * 64,
            intent_payload={"amount": "999.00", "reason": "Hidden outlet"},
            expires_at=timezone.now() + timedelta(minutes=2),
            used_at=timezone.now(),
        )
        self.login(self.manager)
        response = self.client.get(reverse("staff-management"), {"view": "approvals"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item.pk for item in response.context["approval_evidence"]], [visible.pk])
        self.assertContains(response, self.worker.email)
        self.assertContains(response, self.manager.email)
        self.assertContains(response, "amount 20.00")
        self.assertContains(response, "Customer return")
        self.assertNotContains(response, "999.00")
        self.assertNotContains(response, "approver_pin")

    def test_malformed_or_hidden_source_cannot_be_reviewed(self):
        self.login()
        route = reverse("staff-management")
        self.assertEqual(self.client.post(route, {"entity_id": "bad"}).status_code, 400)
        row = next(r for r in self.rows() if r.kind == "cash_variance")
        hidden = PosShift.objects.create(tenant=self.tenant, outlet=self.other, status="closed", expected_cash=20, counted_cash=0, closed_at=timezone.now())
        self.assertEqual(self.client.post(route, self.review_data(row, entity_id=str(hidden.pk))).status_code, 409)
        self.assertEqual(ExceptionReview.objects.count(), 0)

    def test_source_lookup_beyond_display_limit_and_lookback(self):
        self.login()
        refund_row = next(r for r in self.rows() if r.kind == "refund")
        for i in range(51):
            Refund.objects.create(tenant=self.tenant, order=self.order, payment=self.refund.payment, amount=1, idempotency_key=f"extra-refund-{i}")
        rows = self.rows()
        self.assertEqual(len([r for r in rows if r.kind == "refund"]), 50)
        self.assertNotIn(str(self.refund.pk), {r.entity_id for r in rows if r.kind == "refund"})
        # New refunds materially change the review evidence, so a stale
        # fingerprint must fail even when the original refund is beyond the
        # 50-row display limit. Refresh from its scoped source URL.
        response = self.client.post(reverse("staff-management"), self.review_data(refund_row))
        self.assertEqual(response.status_code, 409)
        source = self.client.get(reverse("staff-management-source", args=["refund", self.refund.pk]))
        self.assertEqual(source.status_code, 200)
        refreshed = source.context["exception"]
        self.assertNotEqual(refund_row.fingerprint, refreshed.fingerprint)
        self.assertIn("52 refunds", refreshed.detail)
        self.assertEqual(self.client.post(reverse("staff-management"), self.review_data(refreshed)).status_code, 302)
        self.assertTrue(ExceptionReview.objects.filter(entity_id=self.refund.pk).exists())
        Refund.objects.filter(pk=self.refund.pk).update(created_at=timezone.now()-timedelta(days=60))
        self.assertEqual(self.client.post(reverse("staff-management"), self.review_data(refund_row)).status_code, 409)
        PosShift.objects.filter(pk=self.shift.pk).update(closed_at=timezone.now()-timedelta(days=60))
        self.assertNotIn("cash_variance", {r.kind for r in self.rows()})
        self.assertIn("low_stock", {r.kind for r in self.rows()})

    def test_all_sections_reports_and_dashboard_cache_only_authorized_outlets(self):
        from django.core.cache import cache
        cache.clear()
        hidden_order = Order.objects.create(tenant=self.tenant, outlet=self.other, total=999)
        Payment.objects.create(tenant=self.tenant, order=hidden_order, amount=999, idempotency_key="hidden-payment")
        self.login()
        session = self.client.session
        session[STAFF_SESSION_OUTLET_KEY] = "__all__"
        session.save()
        owner = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(owner.context["staff_dashboard_sales_snapshot"].gross_sales, "1099.00")
        self.login(self.manager)
        session = self.client.session
        session[STAFF_SESSION_OUTLET_KEY] = "__all__"
        session.save()
        response = self.client.get(reverse("staff-sales"))
        self.assertEqual(response.context["summary"]["gross_sales"], Decimal("100"))
        self.assertEqual(response.context["summary"]["refunds_total"], Decimal("20"))
        self.assertNotContains(response, self.other.name)
        csv = self.client.get(reverse("staff-sales"), {"format": "csv"})
        self.assertNotIn("999", csv.content.decode())
        self.assertNotIn(self.other.name, csv.content.decode())
        manager = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(manager.context["staff_dashboard_sales_snapshot"].gross_sales, "100.00")
        cache.clear()

    def test_property_only_team_without_pos_outlets(self):
        property_site = Site.objects.create(tenant=self.tenant, name="Property only")
        user = User.objects.create_user(email="property-manager@test.local", password="Password9!")
        member = Membership.objects.create(tenant=self.tenant, user=user, role=MembershipRole.SITE_MANAGER)
        member.sites.add(property_site)
        receptionist = User.objects.create_user(email="property-reception@test.local", password="Password9!")
        member = Membership.objects.create(tenant=self.tenant, user=receptionist, role=MembershipRole.FRONT_DESK)
        member.sites.add(property_site)
        self.login(user)
        response = self.client.get(reverse("staff-management"), {"view": "team"})
        self.assertContains(response, receptionist.email)
        self.assertNotContains(response, self.worker.email)

    def test_all_exception_sources_and_module_visibility(self):
        from apps.pos.models import OrderLine, OfflineQueuedOperation
        from apps.inventory.models import StockMovement, StockReason
        from apps.purchasing.models import Supplier, PurchaseOrder, PurchaseReceipt
        from apps.finance.models import FinanceCategory, CashbookEntry, FinancePostingLink
        from apps.integrations.models import EfrisSubmission
        from apps.audit.services import log_audit
        self.login()
        self.order.discount_amount = 8
        self.order.save()
        line = OrderLine.objects.create(order=self.order, label="Tea", quantity=1, unit_price=10, line_total=10, line_discount_amount=2, is_voided=True, void_reason="Mistake", voided_at=timezone.now())
        another = OrderLine.objects.create(order=self.order, label="Coffee", quantity=1, unit_price=10, line_total=10, line_discount_amount=2)
        movement = StockMovement.objects.create(tenant=self.tenant,outlet=self.outlet,menu_item=self.balance.menu_item,quantity_change=-4,reason=StockReason.ADJUST_OUT)
        supplier = Supplier.objects.create(tenant=self.tenant,name="Source supplier")
        po = PurchaseOrder.objects.create(tenant=self.tenant,outlet=self.outlet,supplier=supplier,status="partially_received")
        receipt = PurchaseReceipt.objects.create(tenant=self.tenant,purchase_order=po,discrepancy_note="Two units damaged")
        failed = OfflineQueuedOperation.objects.create(tenant=self.tenant,outlet=self.outlet,client_mutation_id="failed-op",operation_type="order_payment",status="failed",payload={"secret":"do-not-show"},error_message="do-not-show")
        old = OfflineQueuedOperation.objects.create(tenant=self.tenant,outlet=self.outlet,client_mutation_id="old-op",operation_type="order_payment",status="pending")
        OfflineQueuedOperation.objects.filter(pk=old.pk).update(created_at=timezone.now()-timedelta(hours=30))
        category = FinanceCategory.objects.create(tenant=self.tenant,name="POS",kind="income")
        entry = CashbookEntry.objects.create(tenant=self.tenant,site=self.site,category=category,amount=10,transaction_date=timezone.localdate())
        fiscal = EfrisSubmission.objects.create(tenant=self.tenant,cashbook_entry=entry,status="failed",last_error="do-not-show")
        FinancePostingLink.objects.create(tenant=self.tenant,cashbook_entry=entry,source_type="pos_payment",source_id=str(self.refund.payment_id))
        hidden_order = Order.objects.create(tenant=self.tenant,outlet=self.other,total=500)
        hidden_payment = Payment.objects.create(tenant=self.tenant,order=hidden_order,amount=500,idempotency_key="fiscal-hidden")
        hidden_entry = CashbookEntry.objects.create(tenant=self.tenant,site=self.site,category=category,amount=500,transaction_date=timezone.localdate())
        hidden_fiscal = EfrisSubmission.objects.create(tenant=self.tenant,cashbook_entry=hidden_entry,status="failed")
        FinancePostingLink.objects.create(tenant=self.tenant,cashbook_entry=hidden_entry,source_type="pos_payment",source_id=str(hidden_payment.pk))
        event = log_audit(tenant_id=self.tenant.pk,user_id=None,action="staff.pin_failed",entity_type="membership",entity_id=str(Membership.objects.get(user=self.worker).pk),payload={"outlet_id":str(self.outlet.pk),"failure_count":2,"locked":False})
        rows = self.rows()
        self.assertTrue({"discount","line_discount","void","stock_adjustment","delivery_discrepancy","efris_failure","offline_conflict","pin_failure"}.issubset({r.kind for r in rows}))
        self.assertNotIn(str(hidden_fiscal.pk),{r.entity_id for r in rows})
        self.assertNotIn("do-not-show",self.client.get(reverse("staff-management")).content.decode())
        for kind in ("efris_failure","offline_conflict","pin_failure","stock_adjustment"):
            source = next(r for r in rows if r.kind == kind)
            self.assertEqual(self.client.get(source.url).status_code,200)
        TenantSettings.objects.create(tenant=self.tenant,enabled_staff_modules=["pos"])
        self.assertFalse({"stock_adjustment","delivery_discrepancy","efris_failure"} & {r.kind for r in self.rows()})

    def test_void_exceptions_show_cashier_attribution_across_sales(self):
        from apps.pos.models import OrderLine
        self.login()
        first_order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, total=20, status="open", currency="UGX",
        )
        second_order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, total=30, status="open", currency="UGX",
        )
        now = timezone.now()
        first = OrderLine.objects.create(
            order=first_order,
            label="First void",
            quantity=1,
            unit_price=20,
            line_total=20,
            is_voided=True,
            void_reason="Wrong scan",
            voided_at=now,
            voided_by=self.worker,
        )
        OrderLine.objects.create(
            order=second_order,
            label="Second void",
            quantity=1,
            unit_price=30,
            line_total=30,
            is_voided=True,
            void_reason="Customer changed item",
            voided_at=now,
            voided_by=self.worker,
        )
        row = next(r for r in self.rows() if r.kind == "void" and r.entity_id == str(first.pk))
        self.assertIn(self.worker.email, row.detail)
        self.assertIn("2 voided lines by this worker in the review window", row.detail)

    def test_no_sale_drawer_events_show_worker_repeat_count(self):
        self.login()
        for index in range(2):
            AuditEvent.objects.create(
                tenant=self.tenant,
                user=self.worker,
                action="pos.drawer_no_sale_opened",
                entity_type="no_sale_drawer",
                entity_id=f"no-sale-{index}",
                payload={
                    "shift_id": str(self.shift.pk),
                    "outlet_id": str(self.outlet.pk),
                    "workstation_id": "",
                    "reason": "Customer requested change",
                },
            )
        rows = [r for r in self.rows() if r.kind == "drawer_no_sale"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(self.worker.email in r.detail for r in rows))
        self.assertTrue(all("2 no-sale openings by this worker" in r.detail for r in rows))
        self.assertEqual(self.client.get(rows[0].url).status_code, 200)

    def test_loss_prevention_exceptions_show_truthful_operator_evidence(self):
        from apps.inventory.models import StockMovement, StockReason
        from apps.pos.models import OrderLine

        self.login()
        self.refund.recorded_by = self.worker
        self.refund.save(update_fields=["recorded_by", "updated_at"])
        self.shift.closed_by = self.manager
        self.shift.save(update_fields=["closed_by", "updated_at"])

        self.order.discount_amount = Decimal("8")
        self.order.save(update_fields=["discount_amount", "updated_at"])
        AuditEvent.objects.create(
            tenant=self.tenant,
            user=self.worker,
            action="order.promotion_applied",
            entity_type="order",
            entity_id=str(self.order.pk),
            payload={"discount_amount": "8.00"},
        )

        discounted = OrderLine.objects.create(
            order=self.order,
            label="Manager discount",
            quantity=1,
            unit_price=10,
            line_total=8,
            line_discount_amount=2,
            pricing_source="manual",
        )
        worker_membership = Membership.objects.get(
            tenant=self.tenant,
            user=self.worker,
        )
        manager_membership = Membership.objects.get(
            tenant=self.tenant,
            user=self.manager,
        )
        approval = SensitiveActionApproval.objects.create(
            tenant=self.tenant,
            requester=worker_membership,
            approver=manager_membership,
            scope_outlet=self.outlet,
            action="discount",
            entity_type="order",
            entity_id=str(self.order.pk),
            request_key="management-margin-override",
            intent_hash="management-margin-override-intent",
            intent_payload={
                "line_id": str(discounted.pk),
                "margin_override_reason": "Clearance item approved",
            },
            expires_at=timezone.now() + timedelta(minutes=2),
            used_at=timezone.now(),
        )
        AuditEvent.objects.create(
            tenant=self.tenant,
            user=self.worker,
            action="order.line_discount_applied",
            entity_type="order_line",
            entity_id=str(discounted.pk),
            payload={
                "order_id": str(self.order.pk),
                "line_discount_amount": "2.00",
                "margin_floor_overridden": True,
                "margin_floor_percent": "30",
                "minimum_unit_price": "9.00",
                "proposed_unit_price": "8.00",
                "margin_override_reason": "Clearance item approved",
                "approval_id": str(approval.pk),
            },
        )
        movement = StockMovement.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.balance.menu_item,
            quantity_change=Decimal("-1"),
            reason=StockReason.ADJUST_OUT,
            note="Damaged during handling",
            created_by=self.worker,
        )

        historical_order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            total=7,
            currency="UGX",
            created_by=self.worker,
        )
        manual = OrderLine.objects.create(
            order=historical_order,
            label="Historical manual price",
            quantity=1,
            unit_price=7,
            line_total=7,
            pricing_source="manual",
        )

        rows = self.rows()
        refund = next(r for r in rows if r.kind == "refund" and r.entity_id == str(self.refund.pk))
        variance = next(r for r in rows if r.kind == "cash_variance" and r.entity_id == str(self.shift.pk))
        order_discount = next(r for r in rows if r.kind == "discount" and r.entity_id == str(self.order.pk))
        line_discount = next(r for r in rows if r.kind == "line_discount" and r.entity_id == str(discounted.pk))
        margin_override = next(
            r for r in rows
            if r.kind == "margin_override"
            and "Clearance item approved" in r.detail
        )
        manual_price = next(r for r in rows if r.kind == "manual_price" and r.entity_id == str(manual.pk))

        self.assertIn(self.worker.email, refund.detail)
        self.assertIn(self.manager.email, variance.detail)
        self.assertIn(self.worker.email, order_discount.detail)
        self.assertIn(self.worker.email, line_discount.detail)
        self.assertIn(self.worker.email, margin_override.detail)
        self.assertIn(self.manager.email, margin_override.detail)
        self.assertIn("floor 30%", margin_override.detail)
        self.assertIn("minimum 9.00", margin_override.detail)
        self.assertIn("sold at 8.00 UGX", margin_override.detail)
        self.assertIn("Clearance item approved", margin_override.detail)
        self.assertIn(self.worker.email, manual_price.detail)
        self.assertIn("exact price-entry operator was not historically recorded", manual_price.detail)

        page = self.client.get(reverse("staff-management"), {"view": "exceptions"})
        patterns = page.context["loss_patterns"]
        worker_pattern = next(
            row for row in patterns["workers"]
            if row["worker"] == self.worker.email
        )
        manager_pattern = next(
            row for row in patterns["workers"]
            if row["worker"] == self.manager.email
        )
        outlet_pattern = next(
            row for row in patterns["outlets"]
            if row["outlet"] == self.outlet.name
        )
        product_pattern = next(
            row for row in patterns["products"]
            if row["product"] == "Manager discount"
        )
        self.assertGreaterEqual(worker_pattern["refunds"], 1)
        self.assertEqual(worker_pattern["line_discounts"], 1)
        self.assertEqual(worker_pattern["margin_overrides"], 1)
        self.assertGreaterEqual(worker_pattern["stock_removals"], 1)
        self.assertGreaterEqual(manager_pattern["cash_variances"], 1)
        self.assertGreaterEqual(outlet_pattern["refunds"], 1)
        self.assertEqual(outlet_pattern["margin_overrides"], 1)
        self.assertEqual(product_pattern["line_discounts"], 1)
        self.assertEqual(product_pattern["margin_overrides"], 1)
        self.assertContains(page, "Repeated loss-prevention patterns")
        self.assertContains(page, self.worker.email)
        self.assertContains(page, "Manager discount")
        self.assertContains(page, "Export pattern CSV")

        exported = self.client.get(
            reverse("staff-management"),
            {"view": "exceptions", "loss_export": "csv"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported["Content-Type"], "text/csv; charset=utf-8")
        body = exported.content.decode()
        self.assertIn(
            "worker,refunds,voids,line_discounts,margin_overrides,cash_variances,stock_removals,total_signals,last_activity",
            body,
        )
        self.assertIn(self.worker.email, body)
        self.assertIn(self.outlet.name, body)
        self.assertIn("Manager discount", body)

        worker_detail = self.client.get(
            reverse(
                "staff-management-loss-pattern",
                args=["worker", worker_pattern["pattern_key"]],
            )
        )
        self.assertEqual(worker_detail.status_code, 200)
        self.assertContains(worker_detail, "Worker evidence")
        self.assertContains(worker_detail, self.worker.email)
        self.assertContains(worker_detail, "Refund")
        self.assertContains(worker_detail, "Margin override")
        self.assertContains(worker_detail, "Clearance item approved")
        self.assertContains(worker_detail, "Stock removal")
        self.assertContains(worker_detail, "Damaged during handling")
        self.assertContains(worker_detail, f"movement={movement.pk}")
        self.assertContains(worker_detail, "Open source")

        outlet_detail = self.client.get(
            reverse(
                "staff-management-loss-pattern",
                args=["outlet", outlet_pattern["pattern_key"]],
            )
        )
        self.assertEqual(outlet_detail.status_code, 200)
        self.assertContains(outlet_detail, "Section evidence")
        self.assertContains(outlet_detail, self.outlet.name)
        self.assertContains(outlet_detail, "Cash variance")

        product_detail = self.client.get(
            reverse(
                "staff-management-loss-pattern",
                args=["product", product_pattern["pattern_key"]],
            )
        )
        self.assertEqual(product_detail.status_code, 200)
        self.assertContains(product_detail, "Product evidence")
        self.assertContains(product_detail, "Manager discount")
        self.assertContains(product_detail, "Margin override")
        self.assertNotContains(product_detail, "Cash variance")
        self.assertNotContains(product_detail, "Refund 20")

        hidden = self.client.get(
            reverse(
                "staff-management-loss-pattern",
                args=["outlet", str(self.other.pk)],
            )
        )
        self.assertEqual(hidden.status_code, 404)

    def test_approved_discount_is_not_duplicated_as_manual_price_exception(self):
        from apps.pos.models import OrderLine
        self.login()
        discounted = OrderLine.objects.create(
            order=self.order,
            label="Approved discount",
            quantity=1,
            unit_price=20,
            line_total=15,
            line_discount_amount=5,
            pricing_source="manual",
        )
        manual = OrderLine.objects.create(
            order=self.order,
            label="Historical manual price",
            quantity=1,
            unit_price=7,
            line_total=7,
            line_discount_amount=0,
            pricing_source="manual",
        )
        rows = self.rows()
        manual_ids = {r.entity_id for r in rows if r.kind == "manual_price"}
        self.assertNotIn(str(discounted.pk), manual_ids)
        self.assertIn(str(manual.pk), manual_ids)
        self.assertIn(str(discounted.pk), {r.entity_id for r in rows if r.kind == "line_discount"})

    def test_exception_view_summarizes_existing_scoped_rows_without_second_ledger(self):
        self.login()
        AuditEvent.objects.create(
            tenant=self.tenant,
            user=self.worker,
            action="pos.drawer_no_sale_opened",
            entity_type="no_sale_drawer",
            entity_id="summary-no-sale",
            payload={
                "shift_id": str(self.shift.pk),
                "outlet_id": str(self.outlet.pk),
                "workstation_id": "",
                "reason": "Change request",
            },
        )
        response = self.client.get(reverse("staff-management"), {"view": "exceptions"})
        self.assertEqual(response.status_code, 200)
        summary = {row["label"]: row for row in response.context["exception_summary"]}
        self.assertGreaterEqual(summary["Money"]["count"], 1)
        self.assertGreaterEqual(summary["Cashier actions"]["count"], 1)
        self.assertGreaterEqual(summary["Stock"]["count"], 1)
        self.assertContains(response, "Loss-prevention snapshot")
        self.assertContains(response, "They are not a second reporting ledger.")

    def test_stock_adjustment_exception_shows_recorded_operator_and_note(self):
        from apps.inventory.models import StockMovement, StockReason

        self.login()
        movement = StockMovement.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.balance.menu_item,
            quantity_change=Decimal("-9"),
            reason=StockReason.WASTE,
            created_by=self.worker,
            note="Damaged carton verified at count",
        )

        row = next(
            item
            for item in self.rows()
            if item.kind == "stock_adjustment"
            and item.entity_id == str(movement.pk)
        )
        self.assertIn(self.worker.email, row.detail)
        self.assertIn("Damaged carton verified at count", row.detail)
        self.assertIn("recorded by", row.detail)

        source = self.client.get(row.url)
        self.assertEqual(source.status_code, 200)
        self.assertContains(source, self.worker.email)
        self.assertContains(source, "Damaged carton verified at count")

    def test_shrink_watch_groups_negative_adjustments_without_cross_tenant_leakage(self):
        from apps.inventory.models import StockMovement, StockReason
        self.login()
        StockMovement.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.balance.menu_item,
            quantity_change=Decimal("-2"),
            reason=StockReason.WASTE,
            created_by=self.worker,
        )
        StockMovement.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.balance.menu_item,
            quantity_change=Decimal("-3"),
            reason=StockReason.ADJUST_OUT,
            created_by=self.worker,
        )
        StockMovement.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.balance.menu_item,
            quantity_change=Decimal("7"),
            reason=StockReason.ADJUST_IN,
            created_by=self.worker,
        )
        foreign_item = MenuItem.objects.create(
            tenant=self.foreign,
            category=MenuCategory.objects.create(tenant=self.foreign, name="Foreign shrink"),
            name="Foreign shrink item",
            unit_price=1,
            track_inventory=True,
        )
        StockMovement.objects.create(
            tenant=self.foreign,
            outlet=self.foreign_outlet,
            menu_item=foreign_item,
            quantity_change=Decimal("-99"),
            reason=StockReason.WASTE,
        )
        response = self.client.get(reverse("staff-management"), {"view": "exceptions"})
        self.assertEqual(response.status_code, 200)
        rows = response.context["shrink_watch"]
        own = next(row for row in rows if row["menu_item_id"] == self.balance.menu_item_id)
        self.assertEqual(own["event_count"], 2)
        self.assertEqual(own["quantity_removed"], Decimal("5"))
        self.assertFalse(any(row["menu_item_id"] == foreign_item.pk for row in rows))
        self.assertContains(response, "Shrink watch")
        self.assertContains(response, "no monetary loss is inferred")

    def test_catalog_price_change_exception_is_outlet_scoped(self):
        self.login()
        visible = AuditEvent.objects.create(
            tenant=self.tenant,
            user=self.owner,
            action="catalog.outlet_price_override_changed",
            entity_type="menu_item_outlet",
            entity_id=str(self.balance.menu_item_id),
            payload={
                "menu_item_id": str(self.balance.menu_item_id),
                "item_name": self.balance.menu_item.name,
                "outlet_id": str(self.outlet.pk),
                "outlet_name": self.outlet.name,
                "before": "10.00",
                "after": "12.00",
            },
        )
        AuditEvent.objects.create(
            tenant=self.tenant,
            user=self.owner,
            action="catalog.outlet_price_override_changed",
            entity_type="menu_item_outlet",
            entity_id=str(self.balance.menu_item_id),
            payload={
                "menu_item_id": str(self.balance.menu_item_id),
                "item_name": self.balance.menu_item.name,
                "outlet_id": str(self.other.pk),
                "outlet_name": self.other.name,
                "before": "10.00",
                "after": "99.00",
            },
        )
        rows = [row for row in self.rows() if row.kind == "price_change"]
        self.assertEqual([row.entity_id for row in rows], [str(visible.pk)])
        self.assertIn("10.00 → 12.00", rows[0].detail)
        self.assertIn(self.owner.email, rows[0].detail)
        response = self.client.get(rows[0].url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selling price changed")
        page = self.client.get(reverse("staff-management"), {"view": "exceptions"})
        summary = {row["label"]: row for row in page.context["exception_summary"]}
        self.assertGreaterEqual(summary["Pricing"]["count"], 1)

    def test_follow_up_ownership_history_and_resolved_case_after_source_clears(self):
        self.login()
        row = next(r for r in self.rows() if r.kind == "low_stock")
        response = self.client.post(reverse("staff-management"),self.review_data(row,status="follow_up",assigned_to=str(self.manager.pk),due_date=str(timezone.localdate()+timedelta(days=2))))
        self.assertEqual(response.status_code,302)
        review = ExceptionReview.objects.get(entity_id=str(self.balance.pk))
        self.assertEqual(review.assigned_to,self.manager)
        self.balance.quantity=10
        self.balance.save()
        self.assertNotIn(str(self.balance.pk),{r.entity_id for r in self.rows()})
        url=reverse("staff-management")+"?view=cases"
        response=self.client.get(url)
        self.assertContains(response,"Checked with worker")
        response=self.client.post(url,{"action":"case","case_id":review.pk,"status":"resolved","note":"Reorder verified"})
        self.assertEqual(response.status_code,302)
        review.refresh_from_db()
        self.assertEqual(review.status,"resolved")
        self.assertEqual(AuditEvent.objects.filter(action="exception.reviewed",entity_id=str(review.pk)).count(),2)
        self.assertEqual(self.balance.quantity,10)
        self.login(self.worker)
        self.assertEqual(self.client.post(url,{"action":"case","case_id":review.pk,"status":"resolved","note":"Tamper"}).status_code,403)

    def test_follow_up_requires_scoped_manager_and_due_date(self):
        self.login()
        row=next(r for r in self.rows() if r.kind=="refund")
        base=self.review_data(row,status="follow_up")
        url=reverse("staff-management")
        for changes in ({},{"assigned_to":str(self.worker.pk),"due_date":str(timezone.localdate())},{"assigned_to":str(self.manager.pk)}):
            self.assertIn(self.client.post(url,{**base,**changes}).status_code,{400,409})
        self.assertFalse(ExceptionReview.objects.filter(entity_id=str(self.refund.pk)).exclude(note="").exists())
        self.assertEqual(self.client.post(url,{**base,"assigned_to":str(self.manager.pk),"due_date":str(timezone.localdate())}).status_code,302)

    def test_old_unresolved_delivery_discrepancy_stays_live_until_resolved(self):
        from apps.audit.services import exception_fingerprint
        from apps.purchasing.models import Supplier, PurchaseOrder, PurchaseReceipt

        self.login()
        ExceptionPolicy.objects.create(tenant=self.tenant, lookback_days=7)
        supplier = Supplier.objects.create(tenant=self.tenant, name="Old discrepancy supplier")
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            supplier=supplier,
            status="partially_received",
        )
        receipt = PurchaseReceipt.objects.create(
            tenant=self.tenant,
            purchase_order=po,
            discrepancy_note="Old shortage still awaiting supplier resolution",
        )
        PurchaseReceipt.objects.filter(pk=receipt.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )
        receipt.refresh_from_db()

        live_ids = {
            r.entity_id for r in self.rows() if r.kind == "delivery_discrepancy"
        }
        self.assertIn(str(receipt.pk), live_ids)

        review = ExceptionReview.objects.create(
            tenant=self.tenant,
            kind="delivery_discrepancy",
            entity_id=str(receipt.pk),
            fingerprint=exception_fingerprint(
                (receipt.discrepancy_note, receipt.updated_at)
            ),
            status="resolved",
            note="Supplier credit confirmed and discrepancy closed.",
            reviewed_by=self.owner,
            scope_outlet=self.outlet,
        )
        live_ids = {
            r.entity_id for r in self.rows() if r.kind == "delivery_discrepancy"
        }
        self.assertNotIn(str(receipt.pk), live_ids)

        response = self.client.get(reverse("staff-management"), {"view": "cases"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            review.pk,
            {case.pk for case in response.context["exception_cases"]},
        )
        source = self.client.get(
            reverse(
                "staff-management-source",
                args=["delivery_discrepancy", receipt.pk],
            )
        )
        self.assertEqual(source.status_code, 200)
        self.assertEqual(source.context["exception"].review.pk, review.pk)
        self.assertIn("Old shortage still awaiting supplier resolution", source.content.decode())

    def test_receiving_discrepancy_appears_from_staff_workflow(self):
        from apps.purchasing.models import Supplier,PurchaseOrder,PurchaseOrderLine,PurchaseReceipt
        self.login()
        supplier=Supplier.objects.create(tenant=self.tenant,name="Receiving supplier")
        po=PurchaseOrder.objects.create(tenant=self.tenant,outlet=self.outlet,supplier=supplier,status="sent")
        line=PurchaseOrderLine.objects.create(purchase_order=po,menu_item=self.balance.menu_item,quantity_ordered=4,unit_cost=Decimal("2"))
        url=reverse("staff-purchasing-order-detail",args=[po.pk])
        response=self.client.post(url,{"action":"receive",f"recv_{line.pk}":"1","discrepancy_note":"One box damaged","delivery_reference":"DEL-1"})
        self.assertEqual(response.status_code,302)
        receipt=PurchaseReceipt.objects.get(purchase_order=po)
        self.assertEqual(receipt.discrepancy_note,"One box damaged")
        self.assertContains(self.client.get(url),"One box damaged")
        self.assertIn(str(receipt.pk),{r.entity_id for r in self.rows() if r.kind=="delivery_discrepancy"})
        self.assertEqual(self.balance.refresh_from_db() or self.balance.quantity,Decimal("3"))

    def test_bad_pin_audited_without_credential_and_thresholds(self):
        from apps.staff.terminal import set_member_pin,verify_member_pin
        member=Membership.objects.get(user=self.worker)
        set_member_pin(member,"123456")
        self.assertIsNone(verify_member_pin(member_id=member.pk,tenant_id=self.tenant.pk,outlet_id=str(self.outlet.pk),pin="wrong"))
        self.assertIsNone(verify_member_pin(member_id=member.pk,tenant_id=self.tenant.pk,outlet_id=str(self.outlet.pk),pin="wrong"))
        failures=AuditEvent.objects.filter(tenant=self.tenant,action="staff.pin_failed")
        self.assertEqual(failures.count(),2)
        self.assertNotIn("wrong",str(list(failures.values("payload"))))
        self.assertNotIn("123456",str(list(failures.values("payload"))))
        ExceptionPolicy.objects.create(tenant=self.tenant,pin_failure_threshold=2)
        self.login()
        self.assertEqual(len([r for r in self.rows() if r.kind=="pin_failure"]),1)
