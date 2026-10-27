from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0032_customer_price_book_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantsettings",
            name="retail_min_margin_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    "Optional minimum gross margin for retail/supermarket items with a complete "
                    "authoritative inventory cost basis. Blank disables margin-floor enforcement."
                ),
                max_digits=5,
                null=True,
                validators=[
                    MinValueValidator(Decimal("0")),
                    MaxValueValidator(Decimal("99.99")),
                ],
            ),
        ),
    ]
