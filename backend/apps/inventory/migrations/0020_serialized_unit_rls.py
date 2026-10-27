from django.db import migrations


def _enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    cursor = schema_editor.connection.cursor()
    for table in ("inventory_inventoryserialunit", "inventory_inventoryserialevent"):
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        cursor.execute(
            f"""CREATE POLICY tenant_isolation ON "{table}"
            FOR ALL USING (
                tenant_id::text = current_setting('app.tenant_id', true)
            );"""
        )


def _disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    cursor = schema_editor.connection.cursor()
    for table in ("inventory_inventoryserialevent", "inventory_inventoryserialunit"):
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0019_serialized_unit_ledger"),
    ]

    operations = [
        migrations.RunPython(_enable_rls, _disable_rls),
    ]
