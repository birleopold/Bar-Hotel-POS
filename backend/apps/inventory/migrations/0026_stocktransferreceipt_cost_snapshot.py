from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0025_stockbalance_average_cost"),
    ]

    operations = [
        migrations.AddField(
            model_name="stocktransferreceipt",
            name="unit_cost_snapshot",
            field=models.DecimalField(
                blank=True,
                help_text="Source outlet weighted-average cost captured when stock was dispatched.",
                max_digits=14,
                decimal_places=4,
                null=True,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="stocktransferreceipt",
            name="cost_basis_complete_snapshot",
            field=models.BooleanField(
                default=False,
                help_text="Whether the transferred units had a complete authoritative source cost basis.",
            ),
        ),
    ]
