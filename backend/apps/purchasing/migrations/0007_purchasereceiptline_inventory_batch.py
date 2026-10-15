from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0006_purchasereceipt_discrepancy_note"),
        ("inventory", "0005_inventorybatch"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasereceiptline",
            name="inventory_batch",
            field=models.ForeignKey(
                to="inventory.inventorybatch",
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True,
                related_name="purchase_receipt_lines",
            ),
        ),
    ]
