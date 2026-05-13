# Extends optional PostgreSQL RLS from 0003 for tables added in later app migrations.

from django.db import migrations


def _enable_extra_rls(schema_editor) -> None:
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

    for t in (
        "catalog_promotion",
        "pos_offlinequeuedoperation",
        "events_eventspace",
        "events_eventbooking",
        "integrations_integrationlink",
        "accounts_userinvite",
    ):
        policy_direct(t)

    policy_sql(
        "catalog_menuitemrecipeline",
        """EXISTS (
            SELECT 1 FROM catalog_menuitem m
            WHERE m.id = catalog_menuitemrecipeline.parent_item_id
            AND m.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "catalog_promotion_outlets",
        """EXISTS (
            SELECT 1 FROM catalog_promotion p
            WHERE p.id = catalog_promotion_outlets.promotion_id
            AND p.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "lodging_roomratewindow",
        """EXISTS (
            SELECT 1 FROM lodging_roomtype rt
            WHERE rt.id = lodging_roomratewindow.room_type_id
            AND rt.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )


def _disable_extra_rls(schema_editor) -> None:
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return
    cursor = conn.cursor()
    tables = (
        "lodging_roomratewindow",
        "catalog_promotion_outlets",
        "catalog_menuitemrecipeline",
        "accounts_userinvite",
        "integrations_integrationlink",
        "events_eventbooking",
        "events_eventspace",
        "pos_offlinequeuedoperation",
        "catalog_promotion",
    )
    for t in tables:
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{t}";')
        cursor.execute(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY;')


def forwards(apps, schema_editor):
    _enable_extra_rls(schema_editor)


def backwards(apps, schema_editor):
    _disable_extra_rls(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0003_postgres_row_level_security"),
        ("accounts", "0002_userinvite"),
        ("catalog", "0004_menuitem_consume_recipe_on_sale_menuitem_kds_station_and_more"),
        ("events", "0001_initial"),
        ("integrations", "0001_initial"),
        ("lodging", "0003_roomratewindow"),
        ("pos", "0004_order_applied_promotion_orderline_kds_station_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
