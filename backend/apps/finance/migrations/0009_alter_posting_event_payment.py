from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("finance", "0008_financepostinglink_source_type")]

    operations = [
        migrations.AlterField(
            model_name="financepostinglink", name="source_type",
            field=models.CharField(max_length=48, choices=[
                ("pos_payment", "POS payment"), ("pos_refund", "POS refund"),
                ("folio_payment", "Folio payment"),
                ("purchase_receive_movement", "Purchase receive movement"),
                ("supplier_payment", "Supplier payment"), ("event_payment", "Event payment"),
            ]),
        ),
    ]
