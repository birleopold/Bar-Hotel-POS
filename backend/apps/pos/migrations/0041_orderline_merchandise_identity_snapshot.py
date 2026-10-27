from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0040_orderline_merchandise_category_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="merchandise_sku_snapshot",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SKU captured for historical merchandise reporting.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="orderline",
            name="inventory_tracked_snapshot",
            field=models.BooleanField(
                blank=True,
                help_text="Whether this merchandise line was inventory tracked at sale time; null means legacy/unknown.",
                null=True,
            ),
        ),
    ]
