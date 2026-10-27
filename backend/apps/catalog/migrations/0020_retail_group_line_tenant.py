from django.db import migrations, models
import django.db.models.deletion


def _backfill_tenant(apps, schema_editor):
    Line = apps.get_model("catalog", "RetailProductGroupLine")
    for line in Line.objects.select_related("group").all().iterator():
        if line.tenant_id != line.group.tenant_id:
            line.tenant_id = line.group.tenant_id
            line.save(update_fields=["tenant"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0019_retail_group_ci_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="retailproductgroupline",
            name="tenant",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="retail_product_group_lines",
                to="tenants.tenant",
            ),
        ),
        migrations.RunPython(_backfill_tenant, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="retailproductgroupline",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="retail_product_group_lines",
                to="tenants.tenant",
            ),
        ),
    ]
