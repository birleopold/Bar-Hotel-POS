from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tenants", "0022_loyalty_policy")]
    operations = [
        migrations.AddField(
            model_name="tenantsettings", name="offline_cash_payment_limit",
            field=models.DecimalField(
                blank=True, null=True, max_digits=14, decimal_places=2,
                validators=[MinValueValidator(Decimal("0.01"))],
                help_text="Optional maximum offline cash payment in the default currency. Blank preserves existing legacy policy.",
            ),
        ),
    ]
