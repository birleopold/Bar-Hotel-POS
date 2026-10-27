from django.db import migrations


TABLES = (
    "pos_pricebook",
    "pos_pricebookrule",
    "pos_customerpricebookassignment",
)


def _enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    cursor = schema_editor.connection.cursor()
    for table in TABLES:
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        cursor.execute(
            f"""CREATE POLICY tenant_isolation ON "{table}"
            FOR ALL USING (
                tenant_id::text = current_setting('app.tenant_id', true)
            );"""
        )


def _disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    cursor = schema_editor.connection.cursor()
    for table in reversed(TABLES):
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0035_customer_price_books"),
        ("tenants", "0031_product_label_queue_rls"),
    ]

    operations = [
        migrations.RunPython(_enable_rls, _disable_rls),
    ]
