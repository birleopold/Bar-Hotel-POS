from django.db import migrations


def enable_owner_report_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("tenants_ownerreportschedule", "tenants_ownerreportdelivery"):
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(f"""CREATE POLICY tenant_isolation ON "{table}"
                FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true))""")


def disable_owner_report_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("tenants_ownerreportschedule", "tenants_ownerreportdelivery"):
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("tenants", "0020_owner_report_scheduling")]
    operations = [migrations.RunPython(enable_owner_report_rls, disable_owner_report_rls)]
