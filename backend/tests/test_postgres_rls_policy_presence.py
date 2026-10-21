"""PostgreSQL migration smoke test, not non-owner RLS enforcement certification.

The CI database owner bypasses ordinary RLS policies. Production certification
must also run queries as a non-owner, non-BYPASSRLS application role.
"""
from django.db import connection
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
            "inventory_stockbalance",
            "pos_order",
            "pos_payment",
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
