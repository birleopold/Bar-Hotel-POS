from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "pos_workstation" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('CREATE POLICY tenant_isolation ON "pos_workstation" FOR ALL USING (tenant_id::text = current_setting(\'app.tenant_id\', true));')


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "pos_workstation";')
        cursor.execute('ALTER TABLE "pos_workstation" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("pos", "0011_workstation_posshift_workstation_and_more")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
