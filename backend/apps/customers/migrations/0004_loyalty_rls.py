from django.db import migrations


def enable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "customers_loyaltyledgerentry" ENABLE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "customers_loyaltyledgerentry"')
        cursor.execute('''CREATE POLICY tenant_isolation ON "customers_loyaltyledgerentry"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true))''')


def disable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "customers_loyaltyledgerentry"')
        cursor.execute('ALTER TABLE "customers_loyaltyledgerentry" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("customers", "0003_loyalty_ledger")]
    operations = [migrations.RunPython(enable, disable)]
