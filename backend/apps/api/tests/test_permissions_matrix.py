from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipRole, User
from apps.finance.models import CashbookEntry, FinanceCategory, FinanceCategoryKind
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class ApiPermissionMatrixTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a-phase2")
        self.other_tenant = Tenant.objects.create(name="Tenant B", slug="tenant-b-phase2")
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

    def test_accountant_cannot_create_inventory_movements(self) -> None:
        headers = self._auth(self.accountant, tenant_id=self.tenant.id)
        response = self.client.post("/api/v1/stock/movements/", {"note": "test"}, format="json", **headers)
        self.assertEqual(response.status_code, 403)

    def test_site_manager_entries_list_respects_site_scope(self) -> None:
        headers = self._auth(self.site_manager, tenant_id=self.tenant.id)
        response = self.client.get("/api/v1/finance/entries/", **headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        returned_ids = {row["id"] for row in rows}
        self.assertIn(str(self.global_entry.id), returned_ids)
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
