"""Safety checks for management audit visibility, redaction and export."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import AuditEvent
from apps.staff.services.audit_reader import (
    audit_view_row, safe_audit_payload, safe_csv_value,
    visible_audit_events,
)
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class StaffAuditReaderTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Audit Tenant", slug="audit-reader-tenant")
        self.site_a = Site.objects.create(tenant=self.tenant, name="A")
        self.site_b = Site.objects.create(tenant=self.tenant, name="B")
        self.outlet_a = Outlet.objects.create(
            site=self.site_a, name="Register A", outlet_type=OutletType.RETAIL,
        )
        self.outlet_b = Outlet.objects.create(
            site=self.site_b, name="Register B", outlet_type=OutletType.RETAIL,
        )
        self.owner = User.objects.create_user(email="audit.owner@example.org")
        self.manager = User.objects.create_user(email="audit.manager@example.org")
        self.worker = User.objects.create_user(email="audit.worker@example.org")
        self.owner_member = Membership.objects.create(
            tenant=self.tenant, user=self.owner, role=MembershipRole.OWNER,
        )
        self.manager_member = Membership.objects.create(
            tenant=self.tenant, user=self.manager, role=MembershipRole.SITE_MANAGER,
        )
        self.manager_member.sites.add(self.site_a)
        self.worker_member = Membership.objects.create(
            tenant=self.tenant, user=self.worker, role=MembershipRole.SERVER,
        )

    def log(self, outlet, action="stock.adjusted"):
        return AuditEvent.objects.create(
            tenant=self.tenant, user=self.owner, action=action,
            entity_type="stock_movement", entity_id="one",
            payload={"outlet_id": str(outlet.pk), "quantity": "-4", "token": "secret"},
        )

    def test_owner_sees_whole_tenant(self):
        self.log(self.outlet_a)
        self.log(self.outlet_b)
        qs, _ = visible_audit_events(
            tenant=self.tenant, membership=self.owner_member, params={},
        )
        self.assertEqual(qs.count(), 2)

    def test_manager_sees_only_assigned_site_audit(self):
        a = self.log(self.outlet_a)
        self.log(self.outlet_b)
        AuditEvent.objects.create(
            tenant=self.tenant, action="secret.out_of_scope",
            entity_type="unknown", entity_id="one", payload={},
        )
        qs, _ = visible_audit_events(
            tenant=self.tenant, membership=self.manager_member, params={},
        )
        self.assertEqual([event.id for event in qs], [a.id])

    def test_non_manager_cannot_view_audit(self):
        self.log(self.outlet_a)
        qs, _ = visible_audit_events(
            tenant=self.tenant, membership=self.worker_member, params={},
        )
        self.assertFalse(qs.exists())

    def test_sensitive_keys_are_redacted_recursively(self):
        redacted = safe_audit_payload({
            "before": {"customer_email": "private@example.org"},
            "token": "TOP-SECRET",
            "pin_hash": "DONT-EXPOSE",
            "after": {"amount": "250000"},
        })
        self.assertEqual(redacted["token"], "[redacted]")
        self.assertEqual(redacted["pin_hash"], "[redacted]")
        self.assertEqual(redacted["before"]["customer_email"], "[redacted]")
        self.assertEqual(redacted["after"]["amount"], "250000")

    def test_csv_formula_injection_is_escaped(self):
        self.assertEqual(safe_csv_value("=1+1"), "'=1+1")
        self.assertEqual(safe_csv_value(" @NOW()"), "' @NOW()")
        self.assertEqual(safe_csv_value("Normal"), "Normal")

    def test_rendered_audit_row_contains_no_token(self):
        event = self.log(self.outlet_a)
        row = audit_view_row(event)
        self.assertNotIn("secret", row["details"])
        self.assertIn("redacted", row["details"])

    def test_api_audit_matches_manager_scope_and_redacts_payload(self):
        a = self.log(self.outlet_a)
        self.log(self.outlet_b)
        client = APIClient()
        client.force_login(self.manager)

        response = client.get(
            "/api/v1/audit-events/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        self.assertEqual([row["id"] for row in rows], [str(a.id)])
        self.assertEqual(rows[0]["payload"]["token"], "[redacted]")
        self.assertEqual(rows[0]["payload"]["quantity"], "-4")

    def test_api_audit_non_manager_receives_no_events(self):
        self.log(self.outlet_a)
        client = APIClient()
        client.force_login(self.worker)
        response = client.get(
            "/api/v1/audit-events/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        self.assertEqual(rows, [])

    def test_wrong_tenant_membership_shows_nothing(self):
        self.log(self.outlet_a)
        another = Tenant.objects.create(name="Other Audit Tenant", slug="other-audit-reader")
        qs, _ = visible_audit_events(
            tenant=another, membership=self.owner_member, params={},
        )
        self.assertFalse(qs.exists())
