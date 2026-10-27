from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0019_supplier_product_code_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasereceiptline",
            name="unit_cost_snapshot",
            field=models.DecimalField(
                blank=True,
                help_text="Supplier unit cost captured when this physical receipt was posted.",
                max_digits=12,
                decimal_places=2,
                null=True,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
    ]
