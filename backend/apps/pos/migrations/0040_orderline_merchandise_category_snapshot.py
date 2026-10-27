from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0039_orderline_cost_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="merchandise_category_snapshot",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Merchandise category name captured when the sale line was created for historical reporting.",
                max_length=128,
            ),
        ),
    ]
