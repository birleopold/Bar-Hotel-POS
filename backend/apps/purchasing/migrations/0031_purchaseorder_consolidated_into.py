from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0030_purchase_receipt_cost_adjustment_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="consolidated_into",
            field=models.ForeignKey(
                blank=True,
                help_text="Approved source request folded into one consolidated supplier draft.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="consolidated_source_requests",
                to="purchasing.purchaseorder",
            ),
        ),
    ]
