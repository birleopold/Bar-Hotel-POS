"""PostgreSQL migration smoke test, not non-owner RLS enforcement certification.

The CI database owner bypasses ordinary RLS policies. Production certification
must also run queries as a non-owner, non-BYPASSRLS application role.
"""
from django.db import connection, transaction
from apps.tenants.models import Tenant, Site, Outlet, OutletType
from apps.pos.models import Order
from django.test import TestCase


class PostgresRlsPolicyPresenceTests(TestCase):
    def test_core_tenant_tables_have_active_rls_policies(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL is required")
        tables = (
            "accounts_membership",
            "catalog_menuitem",
            "customers_customer",
            "finance_cashbookentry",
            "finance_accountingmapping",
            "finance_accountingexportbatch",
            "inventory_stockbalance",
            "pos_order",
            "pos_payment",
            "pos_orderdelivery",
            "pos_outletdeliverysettings",
            "tenants_site",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relname, c.relrowsecurity,
                       EXISTS (
                           SELECT 1 FROM pg_policies p
                           WHERE p.schemaname = n.nspname
                             AND p.tablename = c.relname
                             AND p.policyname = 'tenant_isolation'
                       )
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
                """,
                [list(tables)],
            )
            state = {name: (enabled, has_policy) for name, enabled, has_policy in cursor.fetchall()}
        for table in tables:
            with self.subTest(table=table):
                self.assertIn(table, state)
                self.assertEqual(state[table], (True, True))


class PostgresRlsEnforcementTests(TestCase):
    def test_non_owner_role_cannot_read_other_tenant_orders(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL is required")
        first = Tenant.objects.create(name="RLS first", slug="rls-first")
        second = Tenant.objects.create(name="RLS second", slug="rls-second")
        for tenant in (first, second):
            site = Site.objects.create(tenant=tenant, name="Main")
            outlet = Outlet.objects.create(site=site, name="Till", outlet_type=OutletType.RETAIL)
            Order.objects.create(tenant=tenant, outlet=outlet, currency="UGX", total=100)
        # The migration/CI database owner bypasses RLS; explicitly exercise
        # SELECT through a temporary non-owner role with only table read access.
        role = "rls_ci_reader"
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOLOGIN")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(f"GRANT SELECT ON pos_order TO {role}")
        for tenant in (first, second):
            with self.subTest(tenant=tenant.slug):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f"SET LOCAL ROLE {role}")
                        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.pk)])
                        cursor.execute("SELECT tenant_id::text FROM pos_order")
                        rows = [item[0] for item in cursor.fetchall()]
                        self.assertEqual(rows, [str(tenant.pk)])
        # A request without a tenant GUC must see no order rows at all.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL ROLE {role}")
                cursor.execute("SELECT set_config('app.tenant_id', '', true)")
                cursor.execute("SELECT tenant_id::text FROM pos_order")
                self.assertEqual(cursor.fetchall(), [])

        # Even if the tenant setting names a third, non-existent tenant, it
        # cannot broaden database access to data from either seeded tenant.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL ROLE {role}")
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", ["00000000-0000-0000-0000-000000000001"])
                cursor.execute("SELECT tenant_id::text FROM pos_order")
                self.assertEqual(cursor.fetchall(), [])
