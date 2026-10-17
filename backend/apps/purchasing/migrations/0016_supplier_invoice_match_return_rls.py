from django.db import migrations


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("purchasing_supplierreturn", "purchasing_supplierinvoiceline"):
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            if table == "purchasing_supplierreturn":
                predicate = "tenant_id::text = current_setting('app.tenant_id', true)"
            else:
                predicate = "EXISTS (SELECT 1 FROM purchasing_supplierinvoice i WHERE i.id = invoice_id AND i.tenant_id::text = current_setting('app.tenant_id', true))"
            cursor.execute(f'CREATE POLICY tenant_isolation ON "{table}" FOR ALL USING ({predicate})')


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in ("purchasing_supplierreturn", "purchasing_supplierinvoiceline"):
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0015_supplier_invoice_matches_and_returns")]
    operations = [migrations.RunPython(forward, reverse)]
