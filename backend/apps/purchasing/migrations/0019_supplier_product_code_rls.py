from django.db import migrations

def forward(apps,schema_editor):
    if schema_editor.connection.vendor!="postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        table="purchasing_supplierproductcode"
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        cursor.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}" FOR ALL USING (
                tenant_id::text = current_setting('app.tenant_id', true)
            )'''
        )

def reverse(apps,schema_editor):
    if schema_editor.connection.vendor!="postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        table="purchasing_supplierproductcode"
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

class Migration(migrations.Migration):
    dependencies=[("purchasing","0018_supplier_product_code")]
    operations=[migrations.RunPython(forward,reverse)]