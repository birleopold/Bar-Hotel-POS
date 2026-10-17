from django.db import migrations


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE pos_retailpickup ENABLE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON pos_retailpickup')
        cursor.execute(
            "CREATE POLICY tenant_isolation ON pos_retailpickup "
            "FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true))"
        )


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON pos_retailpickup')
        cursor.execute('ALTER TABLE pos_retailpickup DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("pos", "0027_retail_pickup")]
    operations = [migrations.RunPython(forward, reverse)]
