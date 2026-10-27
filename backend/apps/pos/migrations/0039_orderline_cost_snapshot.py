from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0038_alter_pricebookrule_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="cost_unit_snapshot",
            field=models.DecimalField(
                blank=True,
                help_text="Authoritative weighted-average inventory unit cost captured when the sale posts stock.",
                max_digits=14,
                decimal_places=4,
                null=True,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="orderline",
            name="cost_basis_complete_snapshot",
            field=models.BooleanField(
                default=False,
                help_text="Whether the captured cost represented the full outlet stock basis at sale time.",
            ),
        ),
    ]
