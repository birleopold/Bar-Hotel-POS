from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "purchasing_suppliercreditnote" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "purchasing_suppliercreditnote";')
        cursor.execute("""CREATE POLICY tenant_isolation ON "purchasing_suppliercreditnote"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true));""")


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "purchasing_suppliercreditnote";')
        cursor.execute('ALTER TABLE "purchasing_suppliercreditnote" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0012_suppliercreditnote")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
