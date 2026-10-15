from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "lodging_roomhousekeepingevent" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "lodging_roomhousekeepingevent";')
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "lodging_roomhousekeepingevent"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true));"""
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "lodging_roomhousekeepingevent";')
        cursor.execute('ALTER TABLE "lodging_roomhousekeepingevent" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("lodging", "0012_housekeeping_workflow")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
