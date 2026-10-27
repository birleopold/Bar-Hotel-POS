from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0042_orderline_commission_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="commission_settled_at_snapshot",
            field=models.DateTimeField(
                blank=True,
                help_text="When commission attribution was frozen for the completed sale.",
                null=True,
            ),
        ),
    ]
