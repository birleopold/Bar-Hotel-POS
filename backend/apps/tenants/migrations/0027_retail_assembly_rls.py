from django.db import migrations


def _enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    cursor = schema_editor.connection.cursor()
    table = "catalog_retailassemblycomponent"
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
    table = "catalog_retailassemblycomponent"
    cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
    cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0015_retail_assembly_component"),
        ("tenants", "0026_retail_merchandise_rls"),
    ]

    operations = [
        migrations.RunPython(_enable_rls, _disable_rls),
    ]
