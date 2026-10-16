from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0009_supplierinvoice_rls")]

    operations = [
        migrations.AlterField(
            model_name="supplierinvoice",
            name="amount",
            field=models.DecimalField(
                decimal_places=2, max_digits=14,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AlterField(
            model_name="supplierinvoice",
            name="recorded_by",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supplier_invoices_recorded",
                to="accounts.user",
            ),
        ),
    ]
