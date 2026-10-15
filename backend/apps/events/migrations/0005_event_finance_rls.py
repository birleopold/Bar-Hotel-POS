from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("events_eventquote", "events_eventpayment"):
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
            cursor.execute(f"""CREATE POLICY tenant_isolation ON "{table}"
                FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true));""")


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("events_eventquote", "events_eventpayment"):
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("events", "0004_event_quote_and_payment")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
