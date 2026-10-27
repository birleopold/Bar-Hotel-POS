from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0024_promotion_targets"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="min_target_quantity",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text="Optional minimum qualifying quantity for the targeted product/family/category/brand, or total basket quantity for whole-basket offers.",
                max_digits=10,
                null=True,
                validators=[MinValueValidator(Decimal("0.001"))],
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="coupon_code",
            field=models.CharField(
                blank=True,
                help_text="Optional coupon code. Coded offers are entered explicitly at checkout and are hidden from the normal offer list.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="max_redemptions",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional total number of fully paid orders that may use this offer.",
                null=True,
                validators=[MinValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="max_redemptions_per_customer",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional paid-order limit per identified customer. Anonymous sales are not counted against this customer-specific limit.",
                null=True,
                validators=[MinValueValidator(1)],
            ),
        ),
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.UniqueConstraint(
                Lower("coupon_code"),
                "tenant",
                condition=~models.Q(("coupon_code", "")),
                name="uniq_promotion_coupon_code_ci_tenant",
            ),
        ),
    ]
