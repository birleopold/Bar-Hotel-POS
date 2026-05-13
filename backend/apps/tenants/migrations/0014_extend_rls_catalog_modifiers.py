# Optional PostgreSQL RLS for catalog modifier tables (same pattern as 0004).

from django.db import migrations


def _enable_rls(apps, schema_editor) -> None:
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return
    cursor = conn.cursor()

    def policy_direct(table: str) -> None:
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        cursor.execute(
            f'''
            CREATE POLICY tenant_isolation ON "{table}"
            FOR ALL
            USING (tenant_id::text = current_setting('app.tenant_id', true));
            '''
        )

    def policy_sql(table: str, using: str) -> None:
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        cursor.execute(
            f'CREATE POLICY tenant_isolation ON "{table}" FOR ALL USING ({using});'
        )

    policy_direct("catalog_modifiergroup")
    policy_sql(
        "catalog_modifieroption",
        """EXISTS (
            SELECT 1 FROM catalog_modifiergroup g
            WHERE g.id = catalog_modifieroption.group_id
            AND g.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "catalog_menuitemmodifiergroup",
        """EXISTS (
            SELECT 1 FROM catalog_menuitem m
            WHERE m.id = catalog_menuitemmodifiergroup.menu_item_id
            AND m.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )


def _disable_rls(apps, schema_editor) -> None:
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return
    cursor = conn.cursor()
    for t in (
        "catalog_menuitemmodifiergroup",
        "catalog_modifieroption",
        "catalog_modifiergroup",
    ):
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{t}";')
        cursor.execute(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0008_modifiers_and_line_snapshot"),
        ("tenants", "0013_tenantsettings_business_lines"),
    ]

    operations = [
        migrations.RunPython(_enable_rls, _disable_rls),
    ]
