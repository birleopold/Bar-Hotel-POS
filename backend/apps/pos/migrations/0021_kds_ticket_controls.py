from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pos", "0020_order_customer")]
    operations = [
        migrations.AlterField(
            model_name="orderline", name="kds_status",
            field=models.CharField(max_length=16, default="pending", choices=[
                ("pending", "Pending"), ("accepted", "Accepted"),
                ("in_prep", "In prep"), ("ready", "Ready"), ("served", "Served"),
            ]),
        ),
        migrations.AddField(
            model_name="orderline", name="kds_rush",
            field=models.BooleanField(default=False, help_text="Show this prep item first."),
        ),
        migrations.AddField(
            model_name="orderline", name="kds_status_changed_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
