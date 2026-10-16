from django.db import migrations


def apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "audit_staffnotification" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "audit_staffnotification";')
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "audit_staffnotification"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true));"""
        )


def undo_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "audit_staffnotification";')
        cursor.execute('ALTER TABLE "audit_staffnotification" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("audit", "0006_staffnotification")]
    operations = [migrations.RunPython(apply_rls, undo_rls)]
