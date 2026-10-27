from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0026_stocktransferreceipt_cost_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="retailassemblyrun",
            name="finished_unit_cost_snapshot",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Authoritative component-cost roll-up per finished base unit when available.",
                max_digits=14,
                null=True,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="retailassemblyrun",
            name="cost_basis_complete_snapshot",
            field=models.BooleanField(
                default=False,
                help_text="Whether every component used by this assembly run had a complete authoritative cost basis.",
            ),
        ),
        migrations.AddField(
            model_name="retailassemblyrun",
            name="component_cost_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Component quantities and authoritative unit costs captured for audit at assembly time.",
            ),
        ),
    ]
