from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import AuditEvent, ExceptionPolicy, ExceptionReview
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
        response = self.client.post(reverse("staff-management"), self.review_data(refund_row))
        self.assertEqual(response.status_code, 302)
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
