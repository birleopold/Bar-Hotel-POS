from django.db import migrations

TABLES = ('audit_exceptionpolicy', 'audit_exceptionreview')


def enable(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(f'CREATE POLICY tenant_isolation ON "{table}" FOR ALL USING (tenant_id::text = current_setting(\'app.tenant_id\', true));')


def disable(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [('audit', '0002_exceptionpolicy_exceptionreview')]
    operations = [migrations.RunPython(enable, disable)]
