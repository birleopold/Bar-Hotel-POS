from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "pos_workstationpairing" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('CREATE POLICY tenant_isolation ON "pos_workstationpairing" FOR ALL USING (tenant_id::text = current_setting(\'app.tenant_id\', true));')


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "pos_workstationpairing";')
        cursor.execute('ALTER TABLE "pos_workstationpairing" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("pos", "0014_workstation_requires_pairing_workstationpairing")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
