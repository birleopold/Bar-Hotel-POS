from django.db import migrations


TABLES = ("pos_outletdeliverysettings", "pos_orderdelivery")


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                "FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true)) "
                "WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))"
            )


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in reversed(TABLES):
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("pos", "0030_delivery_fulfillment")]
    operations = [migrations.RunPython(forward, reverse)]
