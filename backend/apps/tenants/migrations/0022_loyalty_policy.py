from decimal import Decimal
from django.db import migrations, models
from django.core.validators import MinValueValidator

class Migration(migrations.Migration):
    dependencies = [("tenants", "0021_owner_report_rls")]
    operations = [
        migrations.AddField(
            model_name="tenantsettings", name="loyalty_enabled",
            field=models.BooleanField(
                default=False, help_text="Award points for fully paid linked sales in the default currency."
            ),
        ),
        migrations.AddField(
            model_name="tenantsettings", name="loyalty_spend_per_point",
            field=models.DecimalField(
                max_digits=14, decimal_places=2, default=Decimal("10000.00"),
                validators=[MinValueValidator(Decimal("0.01"))],
                help_text="Eligible spending needed for one whole loyalty point."
            ),
        ),
    ]
