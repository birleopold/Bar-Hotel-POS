from django.db import migrations


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE "purchasing_purchasereceiptcostadjustment" ENABLE ROW LEVEL SECURITY'
        )
        cursor.execute(
            'DROP POLICY IF EXISTS tenant_isolation ON "purchasing_purchasereceiptcostadjustment"'
        )
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "purchasing_purchasereceiptcostadjustment"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))"""
        )
        cursor.execute(
            'ALTER TABLE "purchasing_purchasereceiptcostadjustmentline" ENABLE ROW LEVEL SECURITY'
        )
        cursor.execute(
            'DROP POLICY IF EXISTS tenant_isolation ON "purchasing_purchasereceiptcostadjustmentline"'
        )
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "purchasing_purchasereceiptcostadjustmentline"
            FOR ALL USING (
                EXISTS (
                    SELECT 1
                    FROM purchasing_purchasereceiptcostadjustment a
                    WHERE a.id = adjustment_id
                      AND a.tenant_id::text = current_setting('app.tenant_id', true)
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1
                    FROM purchasing_purchasereceiptcostadjustment a
                    WHERE a.id = adjustment_id
                      AND a.tenant_id::text = current_setting('app.tenant_id', true)
                )
            )"""
        )


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in (
            "purchasing_purchasereceiptcostadjustmentline",
            "purchasing_purchasereceiptcostadjustment",
        ):
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0029_purchase_receipt_cost_adjustment")]
    operations = [migrations.RunPython(forward, reverse)]
