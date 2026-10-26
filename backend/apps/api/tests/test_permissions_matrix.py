from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipRole, User
from apps.finance.models import CashbookEntry, FinanceCategory, FinanceCategoryKind
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class ApiPermissionMatrixTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a-phase2")
        self.other_tenant = Tenant.objects.create(name="Tenant B", slug="tenant-b-phase2")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "inventory", "purchasing", "finance", "workspace"],
        )
        self.site_allowed = Site.objects.create(tenant=self.tenant, name="HQ")
        self.site_blocked = Site.objects.create(tenant=self.tenant, name="Branch")
        self.outlet = Outlet.objects.create(
            site=self.site_allowed,
            name="Main Bar",
            outlet_type=OutletType.BAR,
        )
        self.accountant = User.objects.create_user(email="accountant@test.local", password="TestPass9!")
        self.site_manager = User.objects.create_user(email="manager@test.local", password="TestPass9!")
        self.accountant_membership = Membership.objects.create(
            user=self.accountant,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        self.site_manager_membership = Membership.objects.create(
            user=self.site_manager,
            tenant=self.tenant,
            role=MembershipRole.SITE_MANAGER,
        )
        self.site_manager_membership.sites.add(self.site_allowed)
        self.category_income = FinanceCategory.objects.create(
            tenant=self.tenant,
            name="Walk-in Sales",
            kind=FinanceCategoryKind.INCOME,
        )
        self.category_expense = FinanceCategory.objects.create(
            tenant=self.tenant,
            name="Utilities",
            kind=FinanceCategoryKind.EXPENSE,
        )
        self.global_entry = CashbookEntry.objects.create(
            tenant=self.tenant,
            category=self.category_income,
            amount=Decimal("75.00"),
            transaction_date=date(2026, 5, 1),
            note="Global line",
            created_by=self.site_manager,
        )
        self.allowed_entry = CashbookEntry.objects.create(
            tenant=self.tenant,
            category=self.category_expense,
            site=self.site_allowed,
            amount=Decimal("20.00"),
            transaction_date=date(2026, 5, 2),
            note="Allowed site line",
            created_by=self.site_manager,
        )
        self.blocked_entry = CashbookEntry.objects.create(
            tenant=self.tenant,
            category=self.category_expense,
            site=self.site_blocked,
            amount=Decimal("30.00"),
            transaction_date=date(2026, 5, 3),
            note="Blocked site line",
            created_by=self.site_manager,
        )
    def _auth(self, user: User, *, tenant_id=None) -> dict:
        self.client.force_login(user)
        if tenant_id is None:
            return {}
        return {"HTTP_X_TENANT_ID": str(tenant_id)}

    def test_missing_tenant_header_denies_protected_endpoint(self) -> None:
        headers = self._auth(self.accountant, tenant_id=None)
        response = self.client.get("/api/v1/finance/categories/", **headers)
        self.assertEqual(response.status_code, 403)

    def test_unknown_tenant_header_is_forbidden(self) -> None:
        headers = self._auth(self.accountant, tenant_id=self.other_tenant.id)
        response = self.client.get("/api/v1/finance/categories/", **headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("error", {}).get("code"), "tenant_forbidden")

    def test_offline_sales_sync_uses_same_floor_operator_roles(self) -> None:
        kitchen = User.objects.create_user(
            email="kitchen-offline@test.local", password="TestPass9!"
        )
        kitchen_membership = Membership.objects.create(
            user=kitchen,
            tenant=self.tenant,
            role=MembershipRole.KITCHEN,
        )
        kitchen_membership.sites.add(self.site_allowed)
        kitchen_membership.outlets.add(self.outlet)
        headers = self._auth(kitchen, tenant_id=self.tenant.id)

        denied = self.client.post(
            "/api/v1/pos/offline-sync/",
            {},
            format="json",
            **headers,
        )
        self.assertEqual(denied.status_code, 403)
        batch_denied = self.client.post(
            "/api/v1/pos/offline-sync/batch/",
            {"operations": []},
            format="json",
            **headers,
        )
        self.assertEqual(batch_denied.status_code, 403)

        server = User.objects.create_user(
            email="server-offline@test.local", password="TestPass9!"
        )
        server_membership = Membership.objects.create(
            user=server,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        server_membership.sites.add(self.site_allowed)
        server_membership.outlets.add(self.outlet)
        headers = self._auth(server, tenant_id=self.tenant.id)

        allowed_to_validate = self.client.post(
            "/api/v1/pos/offline-sync/",
            {},
            format="json",
            **headers,
        )
        self.assertEqual(allowed_to_validate.status_code, 400)

    def test_register_shift_api_matches_pos_read_roles(self) -> None:
        kitchen = User.objects.create_user(
            email="kitchen-shifts@test.local", password="TestPass9!"
        )
        kitchen_membership = Membership.objects.create(
            user=kitchen,
            tenant=self.tenant,
            role=MembershipRole.KITCHEN,
        )
        kitchen_membership.sites.add(self.site_allowed)
        kitchen_membership.outlets.add(self.outlet)
        headers = self._auth(kitchen, tenant_id=self.tenant.id)

        denied = self.client.get("/api/v1/pos/shifts/", **headers)
        self.assertEqual(denied.status_code, 403)

        server = User.objects.create_user(
            email="server-shifts@test.local", password="TestPass9!"
        )
        server_membership = Membership.objects.create(
            user=server,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        server_membership.sites.add(self.site_allowed)
        server_membership.outlets.add(self.outlet)
        headers = self._auth(server, tenant_id=self.tenant.id)

        allowed = self.client.get("/api/v1/pos/shifts/", **headers)
        self.assertEqual(allowed.status_code, 200)

    def test_general_order_api_excludes_kitchen_but_keeps_server_floor_access(self) -> None:
        kitchen = User.objects.create_user(
            email="kitchen-order-api@test.local", password="TestPass9!"
        )
        kitchen_membership = Membership.objects.create(
            user=kitchen,
            tenant=self.tenant,
            role=MembershipRole.KITCHEN,
        )
        kitchen_membership.sites.add(self.site_allowed)
        kitchen_membership.outlets.add(self.outlet)
        headers = self._auth(kitchen, tenant_id=self.tenant.id)

        listing = self.client.get("/api/v1/orders/", **headers)
        self.assertEqual(listing.status_code, 403)
        mutation = self.client.post("/api/v1/orders/", {}, format="json", **headers)
        self.assertEqual(mutation.status_code, 403)

        server = User.objects.create_user(
            email="server-order-api@test.local", password="TestPass9!"
        )
        server_membership = Membership.objects.create(
            user=server,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        server_membership.sites.add(self.site_allowed)
        server_membership.outlets.add(self.outlet)
        headers = self._auth(server, tenant_id=self.tenant.id)

        listing = self.client.get("/api/v1/orders/", **headers)
        self.assertEqual(listing.status_code, 200)
        table_create = self.client.post(
            "/api/v1/tables/",
            {"outlet": str(self.outlet.pk), "label": "Server-created"},
            format="json",
            **headers,
        )
        self.assertEqual(table_create.status_code, 403)

    def test_floor_staff_cannot_read_inventory_events_or_lodging_apis(self) -> None:
        settings = self.tenant.settings
        settings.business_lines = ["supermarket", "events", "lodging"]
        settings.enabled_staff_modules = [
            "pos", "inventory", "purchasing", "finance",
            "events", "lodging", "workspace",
        ]
        settings.save(update_fields=["business_lines", "enabled_staff_modules", "updated_at"])

        server = User.objects.create_user(
            email="scope-server@test.local", password="TestPass9!"
        )
        membership = Membership.objects.create(
            user=server,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        membership.sites.add(self.site_allowed)
        membership.outlets.add(self.outlet)
        headers = self._auth(server, tenant_id=self.tenant.id)

        for url in (
            "/api/v1/stock/balances/",
            "/api/v1/events/spaces/",
            "/api/v1/lodging/rooms/",
        ):
            with self.subTest(url=url):
                response = self.client.get(url, **headers)
                self.assertEqual(response.status_code, 403)

        headers = self._auth(self.accountant, tenant_id=self.tenant.id)
        inventory = self.client.get("/api/v1/stock/balances/", **headers)
        self.assertEqual(inventory.status_code, 200)

    def test_floor_staff_cannot_read_finance_api(self) -> None:
        server = User.objects.create_user(
            email="finance-server@test.local", password="TestPass9!"
        )
        membership = Membership.objects.create(
            user=server,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        membership.sites.add(self.site_allowed)
        membership.outlets.add(self.outlet)
        headers = self._auth(server, tenant_id=self.tenant.id)

        categories = self.client.get("/api/v1/finance/categories/", **headers)
        self.assertEqual(categories.status_code, 403)
        entries = self.client.get("/api/v1/finance/entries/", **headers)
        self.assertEqual(entries.status_code, 403)

    def test_accountant_can_read_but_not_write_finance(self) -> None:
        headers = self._auth(self.accountant, tenant_id=self.tenant.id)
        read_response = self.client.get("/api/v1/finance/categories/", **headers)
        self.assertEqual(read_response.status_code, 200)

        write_response = self.client.post(
            "/api/v1/finance/categories/",
            {"name": "Other Income", "kind": FinanceCategoryKind.INCOME, "sort_order": 1},
            format="json",
            **headers,
        )
        self.assertEqual(write_response.status_code, 403)

    def test_floor_staff_cannot_mutate_shared_catalog(self) -> None:
        server = User.objects.create_user(
            email="catalog-server@test.local", password="TestPass9!"
        )
        membership = Membership.objects.create(
            user=server,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        membership.sites.add(self.site_allowed)
        membership.outlets.add(self.outlet)
        headers = self._auth(server, tenant_id=self.tenant.id)

        response = self.client.post(
            "/api/v1/menu/categories/",
            {"name": "Unauthorized category", "sort_order": 1},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_mutate_shared_catalog(self) -> None:
        owner = User.objects.create_user(
            email="catalog-owner@test.local", password="TestPass9!"
        )
        Membership.objects.create(
            user=owner,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        headers = self._auth(owner, tenant_id=self.tenant.id)
        response = self.client.post(
            "/api/v1/menu/categories/",
            {"name": "Owner category", "sort_order": 1},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 201)

    def test_accountant_cannot_create_inventory_movements(self) -> None:
        headers = self._auth(self.accountant, tenant_id=self.tenant.id)
        response = self.client.post("/api/v1/stock/movements/", {"note": "test"}, format="json", **headers)
        self.assertEqual(response.status_code, 403)

    def test_sales_reports_match_staff_role_boundary(self) -> None:
        server = User.objects.create_user(
            email="server-report@test.local", password="TestPass9!"
        )
        server_membership = Membership.objects.create(
            user=server,
            tenant=self.tenant,
            role=MembershipRole.SERVER,
        )
        server_membership.sites.add(self.site_allowed)
        server_membership.outlets.add(self.outlet)

        headers = self._auth(server, tenant_id=self.tenant.id)
        denied = self.client.get(
            "/api/v1/reports/sales-summary/?date_from=2026-05-01&date_to=2026-05-31",
            **headers,
        )
        self.assertEqual(denied.status_code, 403)

        headers = self._auth(self.accountant, tenant_id=self.tenant.id)
        allowed = self.client.get(
            "/api/v1/reports/sales-summary/?date_from=2026-05-01&date_to=2026-05-31",
            **headers,
        )
        self.assertEqual(allowed.status_code, 200)

    def test_site_manager_entries_list_respects_site_scope(self) -> None:
        headers = self._auth(self.site_manager, tenant_id=self.tenant.id)
        response = self.client.get("/api/v1/finance/entries/", **headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        returned_ids = {row["id"] for row in rows}
        # Tenant-wide records without a branch are outside an assigned branch scope.
        self.assertNotIn(str(self.global_entry.id), returned_ids)
        self.assertIn(str(self.allowed_entry.id), returned_ids)
        self.assertNotIn(str(self.blocked_entry.id), returned_ids)

    def test_site_manager_cannot_create_entry_for_blocked_site(self) -> None:
        headers = self._auth(self.site_manager, tenant_id=self.tenant.id)
        response = self.client.post(
            "/api/v1/finance/entries/",
            {
                "category": str(self.category_expense.id),
                "site": str(self.site_blocked.id),
                "amount": "44.00",
                "transaction_date": "2026-05-04",
                "reference": "INV-1",
                "note": "Blocked site attempt",
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 400)
        details = response.json().get("error", {}).get("details", {})
        self.assertIn("site", details)

    def test_site_manager_can_create_entry_for_allowed_site(self) -> None:
        headers = self._auth(self.site_manager, tenant_id=self.tenant.id)
        response = self.client.post(
            "/api/v1/finance/entries/",
            {
                "category": str(self.category_expense.id),
                "site": str(self.site_allowed.id),
                "amount": "18.50",
                "transaction_date": "2026-05-05",
                "reference": "INV-2",
                "note": "Allowed site entry",
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["site"], str(self.site_allowed.id))
        self.assertEqual(payload["created_by_id"], str(self.site_manager.id))
