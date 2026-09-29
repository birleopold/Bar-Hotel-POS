from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("finance", "0002_financepostinglink")]

    operations = [
        migrations.AlterField(
            model_name="financepostinglink",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("pos_payment", "POS payment"),
                    ("pos_refund", "POS refund"),
                    ("purchase_receive_movement", "Purchase receive movement"),
                ],
                max_length=48,
            ),
        ),
    ]
