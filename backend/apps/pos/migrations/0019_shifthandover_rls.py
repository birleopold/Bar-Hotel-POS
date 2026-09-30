from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "pos_shifthandover" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('CREATE POLICY tenant_isolation ON "pos_shifthandover" FOR ALL USING (tenant_id::text = current_setting(\'app.tenant_id\', true));')


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "pos_shifthandover";')
        cursor.execute('ALTER TABLE "pos_shifthandover" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("pos", "0018_shifthandover")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
