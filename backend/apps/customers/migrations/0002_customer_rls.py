from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "customers_customer" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('CREATE POLICY tenant_isolation ON "customers_customer" FOR ALL USING (tenant_id::text = current_setting(\'app.tenant_id\', true));')


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "customers_customer";')
        cursor.execute('ALTER TABLE "customers_customer" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("customers", "0001_initial")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
