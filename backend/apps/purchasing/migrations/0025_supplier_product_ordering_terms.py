from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0024_rfq_supplier_quotes"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierproductcode",
            name="minimum_order_quantity",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text="Optional minimum base-stock quantity when ordering this product from this supplier.",
                max_digits=14,
                null=True,
                validators=[MinValueValidator(Decimal("0.001"))],
            ),
        ),
        migrations.AddField(
            model_name="supplierproductcode",
            name="expected_lead_days",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional expected calendar days from order to delivery for this supplier/product relationship.",
                null=True,
            ),
        ),
    ]
