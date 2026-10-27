from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    CommissionRule,
    Membership,
    MembershipRole,
    SalesTarget,
    User,
)
from apps.catalog.models import MenuCategory, MenuItem
from apps.pos.models import (
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    Refund,
    SupermarketLineReturn,
)
from apps.pos.services.commissions import snapshot_order_commissions
from apps.pos.services.payments import record_order_payment
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_KEY,
    STAFF_SESSION_SITE_KEY,
    STAFF_SESSION_TENANT_KEY,
)
from apps.staff.services.commissions import build_commission_report
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class CommissionWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Commission Test",
            slug="commission-test",
        )
        TenantSettings.objects.update_or_create(
            tenant=self.tenant,
            defaults={
                "business_lines": ["supermarket"],
                "enabled_staff_modules": ["pos", "sales", "inventory"],
                "default_currency": "UGX",
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
            name="Other shop",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(
            email="commission-worker@test.local",
            password="Password9!",
        )
        self.membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=MembershipRole.SERVER,
        )
        self.membership.sites.add(self.site)
        self.membership.outlets.add(self.outlet)

        self.manager = User.objects.create_user(
            email="commission-manager@test.local",
            password="Password9!",
        )
        self.manager_membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.manager,
            role=MembershipRole.OUTLET_MANAGER,
        )
        self.manager_membership.sites.add(self.site)
        self.manager_membership.outlets.add(self.outlet)

        self.owner = User.objects.create_user(
            email="commission-owner@test.local",
            password="Password9!",
        )
        self.owner_membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.owner,
            role=MembershipRole.OWNER,
        )

        self.category = MenuCategory.objects.create(
            tenant=self.tenant,
            name="Electronics",
        )
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="USB Cable",
            unit_price=Decimal("100.00"),
            track_inventory=False,
        )

    def _order(self, *, outlet=None, user=None, amount="100.00"):
        amount = Decimal(amount)
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=outlet or self.outlet,
            status=OrderStatus.OPEN,
            subtotal=amount,
            tax_total=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total=amount,
            created_by=user or self.user,
        )
        line = OrderLine.objects.create(
            order=order,
            menu_item=self.item,
            label=self.item.name,
            quantity=Decimal("1"),
            unit_price=amount,
            line_total=amount,
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

    def test_commission_snapshots_only_at_final_payment_and_stay_immutable(self):
        CommissionRule.objects.create(
            tenant=self.tenant,
            name="Tenant default",
            rate_percent=Decimal("2.00"),
            created_by=self.owner,
        )
        CommissionRule.objects.create(
            tenant=self.tenant,
            name="Employee rule",
            membership=self.membership,
            rate_percent=Decimal("3.00"),
            created_by=self.owner,
        )
        CommissionRule.objects.create(
            tenant=self.tenant,
            name="Category rule",
            category=self.category,
            rate_percent=Decimal("4.00"),
            created_by=self.owner,
        )
        specific = CommissionRule.objects.create(
            tenant=self.tenant,
            name="Worker USB rule",
            membership=self.membership,
            menu_item=self.item,
            rate_percent=Decimal("5.00"),
            created_by=self.owner,
        )
        order, line = self._order()

        record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("40.00"),
            method="cash",
            idempotency_key="commission-partial",
        )
        line.refresh_from_db()
        self.assertIsNone(line.commission_base_snapshot)
        self.assertIsNone(line.commission_amount_snapshot)

        record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("60.00"),
            method="cash",
            idempotency_key="commission-final",
        )
        line.refresh_from_db()
        self.assertEqual(line.sales_attributed_membership_id, self.membership.pk)
        self.assertEqual(line.commission_rule_name_snapshot, "Worker USB rule")
        self.assertEqual(line.commission_base_snapshot, Decimal("100.00"))
        self.assertEqual(line.commission_rate_percent_snapshot, Decimal("5.00"))
        self.assertEqual(line.commission_amount_snapshot, Decimal("5.00"))
        self.assertIsNotNone(line.commission_settled_at_snapshot)

        specific.rate_percent = Decimal("20.00")
        specific.save(update_fields=["rate_percent", "updated_at"])
        snapshot_order_commissions(order=order)
        line.refresh_from_db()
        self.assertEqual(line.commission_rate_percent_snapshot, Decimal("5.00"))
        self.assertEqual(line.commission_amount_snapshot, Decimal("5.00"))

    def test_returns_and_refunds_reverse_commission_across_periods(self):
        CommissionRule.objects.create(
            tenant=self.tenant,
            name="Worker rate",
            membership=self.membership,
            rate_percent=Decimal("5.00"),
            created_by=self.owner,
        )

        old_order, old_line = self._order()
        old_payment, _ = record_order_payment(
            order=old_order,
            user=self.user,
            amount=Decimal("100.00"),
            method="cash",
            idempotency_key="commission-old-sale",
        )
        old_time = timezone.now() - timedelta(days=40)
        OrderLine.objects.filter(pk=old_line.pk).update(
            commission_settled_at_snapshot=old_time
        )

        mapped_refund = Refund.objects.create(
            tenant=self.tenant,
            order=old_order,
            payment=old_payment,
            amount=Decimal("50.00"),
            reason="Half returned",
            idempotency_key="commission-mapped-refund",
            recorded_by=self.manager,
        )
        SupermarketLineReturn.objects.create(
            refund=mapped_refund,
            tenant=self.tenant,
            order=old_order,
            order_line=old_line,
            quantity=Decimal("0.5"),
            reason="Half returned",
            restocked=False,
            created_by=self.manager,
            idempotency_key="commission-half-return",
        )

        general_order, general_line = self._order()
        general_payment, _ = record_order_payment(
            order=general_order,
            user=self.user,
            amount=Decimal("100.00"),
            method="cash",
            idempotency_key="commission-general-sale",
        )
        OrderLine.objects.filter(pk=general_line.pk).update(
            commission_settled_at_snapshot=old_time
        )
        Refund.objects.create(
            tenant=self.tenant,
            order=general_order,
            payment=general_payment,
            amount=Decimal("20.00"),
            reason="General order refund",
            idempotency_key="commission-general-refund",
            recorded_by=self.manager,
        )

        today = timezone.localdate()
        result = build_commission_report(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertEqual(len(result["workers"]), 1)
        row = result["workers"][0]
        self.assertEqual(row["gross_sales"], Decimal("0.00"))
        self.assertEqual(row["sales_reversal"], Decimal("70.00"))
        self.assertEqual(row["mapped_return_reversal"], Decimal("2.50"))
        self.assertEqual(row["allocated_refund_reversal"], Decimal("1.00"))
        self.assertEqual(row["total_reversal"], Decimal("3.50"))
        self.assertEqual(row["net_commission"], Decimal("-3.50"))
        self.assertEqual(result["net_commission"], Decimal("-3.50"))

    def test_target_progress_and_management_report_stay_in_scope(self):
        CommissionRule.objects.create(
            tenant=self.tenant,
            name="Worker rate",
            membership=self.membership,
            rate_percent=Decimal("10.00"),
            created_by=self.owner,
        )
        order, line = self._order()
        record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("100.00"),
            method="cash",
            idempotency_key="commission-target-sale",
        )

        other_user = User.objects.create_user(
            email="commission-other@test.local",
            password="Password9!",
        )
        other_membership = Membership.objects.create(
            tenant=self.tenant,
            user=other_user,
            role=MembershipRole.SERVER,
        )
        other_membership.sites.add(self.other_site)
        other_membership.outlets.add(self.other_outlet)
        other_order, _ = self._order(
            outlet=self.other_outlet,
            user=other_user,
            amount="900.00",
        )
        record_order_payment(
            order=other_order,
            user=other_user,
            amount=Decimal("900.00"),
            method="cash",
            idempotency_key="commission-hidden-sale",
        )

        today = timezone.localdate()
        SalesTarget.objects.create(
            tenant=self.tenant,
            membership=self.membership,
            period_start=today,
            period_end=today,
            target_amount=Decimal("200.00"),
            created_by=self.manager,
        )

        result = build_commission_report(
            tenant_id=self.tenant.pk,
            date_from=today,
            date_to=today,
            allowed_outlet_ids=[self.outlet.pk],
            currency="UGX",
        )
        self.assertEqual(len(result["workers"]), 1)
        row = result["workers"][0]
        self.assertEqual(row["worker"], self.user.email)
        self.assertEqual(row["net_sales"], Decimal("100.00"))
        self.assertEqual(row["net_commission"], Decimal("10.00"))
        self.assertEqual(row["target_amount"], Decimal("200.00"))
        self.assertEqual(row["target_progress_percent"], Decimal("50.0"))

        client = self._login(self.manager)
        page = client.get(
            reverse("staff-management-commissions"),
            {"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.user.email)
        self.assertNotContains(page, other_user.email)
        self.assertContains(page, "10.00")
        self.assertContains(page, "50.0%")

        exported = client.get(
            reverse("staff-management-commissions"),
            {
                "date_from": today.isoformat(),
                "date_to": today.isoformat(),
                "export": "csv",
            },
        )
        self.assertEqual(exported.status_code, 200)
        body = exported.content.decode()
        self.assertIn(self.user.email, body)
        self.assertNotIn(other_user.email, body)
        self.assertIn("net_commission", body)

    def test_commission_rule_admin_is_owner_only_and_tenant_scoped(self):
        foreign = Tenant.objects.create(name="Foreign", slug="commission-foreign")
        TenantSettings.objects.update_or_create(
            tenant=foreign,
            defaults={"business_lines": ["supermarket"]},
        )
        foreign_category = MenuCategory.objects.create(
            tenant=foreign,
            name="Private",
        )

        manager_client = self._login(self.manager)
        self.assertEqual(
            manager_client.get(reverse("staff-workspace-commission-rules")).status_code,
            403,
        )

        owner_client = self._login(self.owner)
        response = owner_client.post(
            reverse("staff-workspace-commission-rule-create"),
            {
                "name": "Cross tenant",
                "membership": "",
                "menu_item": "",
                "category": str(foreign_category.pk),
                "rate_percent": "5",
                "effective_from": "",
                "effective_to": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(
            CommissionRule.objects.filter(
                tenant=self.tenant,
                name="Cross tenant",
            ).exists()
        )
