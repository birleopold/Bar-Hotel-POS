from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0032_supermarket_return_idempotency"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="service_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("dine_in", "Dine in"),
                    ("takeaway", "Takeaway"),
                    ("counter", "Counter sale"),
                    ("bar_tab", "Bar tab"),
                ],
                default="",
                help_text="Operational hospitality order type; blank preserves legacy/non-hospitality orders.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="guest_count",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Number of covers for hospitality service; null when not recorded or not applicable.",
                null=True,
                validators=[MinValueValidator(1), MaxValueValidator(999)],
            ),
        ),
    ]
