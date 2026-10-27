from django.db import migrations


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE "tenants_trainingworkspacestate" ENABLE ROW LEVEL SECURITY'
        )
        cursor.execute(
            'DROP POLICY IF EXISTS tenant_isolation ON "tenants_trainingworkspacestate"'
        )
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "tenants_trainingworkspacestate"
            FOR ALL
            USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))"""
        )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'DROP POLICY IF EXISTS tenant_isolation ON "tenants_trainingworkspacestate"'
        )
        cursor.execute(
            'ALTER TABLE "tenants_trainingworkspacestate" DISABLE ROW LEVEL SECURITY'
        )


class Migration(migrations.Migration):
    dependencies = [("tenants", "0035_training_workspace_state")]
    operations = [migrations.RunPython(forwards, backwards)]
