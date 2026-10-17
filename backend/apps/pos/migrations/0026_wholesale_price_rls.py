from django.db import migrations


def policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "pos_wholesalepricerule" ENABLE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "pos_wholesalepricerule"')
        cursor.execute(
            "CREATE POLICY tenant_isolation ON pos_wholesalepricerule "
            "FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true))"
        )


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "pos_wholesalepricerule"')
        cursor.execute('ALTER TABLE "pos_wholesalepricerule" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("pos", "0025_wholesale_price_rule")]
    operations = [migrations.RunPython(policies, reverse)]
