from django.db import migrations


def secure(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute('ALTER TABLE "pos_workstationhardwarecheck" ENABLE ROW LEVEL SECURITY')
        cur.execute('DROP POLICY IF EXISTS tenant_isolation ON "pos_workstationhardwarecheck"')
        cur.execute('''CREATE POLICY tenant_isolation ON "pos_workstationhardwarecheck"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true))''')


def rollback(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute('DROP POLICY IF EXISTS tenant_isolation ON "pos_workstationhardwarecheck"')
        cur.execute('ALTER TABLE "pos_workstationhardwarecheck" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("pos", "0023_hardware_checks")]
    operations = [migrations.RunPython(secure, rollback)]
