from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0025_promotion_coupon_limits"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(max_redemptions__isnull=True)
                    | models.Q(max_redemptions_per_customer__isnull=True)
                    | models.Q(max_redemptions_per_customer__lte=models.F("max_redemptions"))
                ),
                name="promotion_customer_limit_within_total",
            ),
        ),
    ]
