from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0028_stock_transfer_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="stocktransferrequest",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
