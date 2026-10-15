from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "purchasing_supplierinvoice" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "purchasing_supplierinvoice";')
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "purchasing_supplierinvoice"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true));"""
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "purchasing_supplierinvoice";')
        cursor.execute('ALTER TABLE "purchasing_supplierinvoice" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0008_supplierinvoice")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
