from django.db import migrations


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE "pos_workstationdevice" ENABLE ROW LEVEL SECURITY'
        )
        cursor.execute(
            'DROP POLICY IF EXISTS tenant_isolation ON "pos_workstationdevice"'
        )
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "pos_workstationdevice"
            FOR ALL
            USING (
                tenant_id::text = current_setting('app.tenant_id', true)
            )
            WITH CHECK (
                tenant_id::text = current_setting('app.tenant_id', true)
            )"""
        )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'DROP POLICY IF EXISTS tenant_isolation ON "pos_workstationdevice"'
        )
        cursor.execute(
            'ALTER TABLE "pos_workstationdevice" DISABLE ROW LEVEL SECURITY'
        )


class Migration(migrations.Migration):
    dependencies = [("pos", "0044_workstation_device")]
    operations = [migrations.RunPython(forwards, backwards)]
