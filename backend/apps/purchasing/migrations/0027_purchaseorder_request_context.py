from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0026_supplier_price_record"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="needed_by",
            field=models.DateField(
                blank=True,
                help_text="Requester business need date; separate from supplier expected delivery date.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="purchaseorder",
            name="request_reason",
            field=models.CharField(
                blank=True,
                help_text="Why the stock is needed or what business event triggered the request.",
                max_length=512,
            ),
        ),
    ]
