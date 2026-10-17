from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "inventory_stocktransferreceipt" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "inventory_stocktransferreceipt";')
        cursor.execute("""
            CREATE POLICY tenant_isolation ON "inventory_stocktransferreceipt"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true));
        """)


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "inventory_stocktransferreceipt";')
        cursor.execute('ALTER TABLE "inventory_stocktransferreceipt" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("inventory", "0011_stocktransferreceipt")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
