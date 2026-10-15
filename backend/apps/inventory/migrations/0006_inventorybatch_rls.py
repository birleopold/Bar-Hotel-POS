from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "inventory_inventorybatch" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "inventory_inventorybatch";')
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "inventory_inventorybatch"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true));"""
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "inventory_inventorybatch";')
        cursor.execute('ALTER TABLE "inventory_inventorybatch" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("inventory", "0005_inventorybatch")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
