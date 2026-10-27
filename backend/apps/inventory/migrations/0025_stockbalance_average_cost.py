from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0024_serial_case_insensitive_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockbalance",
            name="average_unit_cost",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                help_text="Weighted average unit cost for this outlet balance when cost_basis_complete is true.",
            ),
        ),
        migrations.AddField(
            model_name="stockbalance",
            name="cost_basis_complete",
            field=models.BooleanField(
                default=False,
                help_text="True only when the full on-hand quantity has an authoritative cost basis.",
            ),
        ),
    ]
