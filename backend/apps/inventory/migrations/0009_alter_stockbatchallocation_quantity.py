from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0008_stockbatchallocation_rls")]

    operations = [
        migrations.AlterField(
            model_name="stockbatchallocation",
            name="quantity",
            field=models.DecimalField(
                decimal_places=3, max_digits=14,
                validators=[MinValueValidator(Decimal("0.001"))],
            ),
        ),
    ]
