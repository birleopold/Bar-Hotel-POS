from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0033_order_service_mode_guest_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="seat_number",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Optional dine-in seat assignment used for restaurant service and later bill splitting.",
                null=True,
                validators=[MinValueValidator(1), MaxValueValidator(999)],
            ),
        ),
    ]
