from decimal import Decimal

from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_commissionrule_salestarget"),
        ("pos", "0041_orderline_merchandise_identity_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="sales_attributed_membership",
            field=models.ForeignKey(blank=True, help_text="Worker credited with this line when the sale was fully settled.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attributed_order_lines", to="accounts.membership"),
        ),
        migrations.AddField(
            model_name="orderline",
            name="commission_rule_name_snapshot",
            field=models.CharField(blank=True, default="", help_text="Commission rule name captured at final settlement.", max_length=80),
        ),
        migrations.AddField(
            model_name="orderline",
            name="commission_base_snapshot",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Net line revenue used to calculate commission at final settlement.", max_digits=14, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))]),
        ),
        migrations.AddField(
            model_name="orderline",
            name="commission_rate_percent_snapshot",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Commission percentage captured at final settlement.", max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0")), django.core.validators.MaxValueValidator(Decimal("100"))]),
        ),
        migrations.AddField(
            model_name="orderline",
            name="commission_amount_snapshot",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Commission earned on this line before later return/refund reversals.", max_digits=14, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))]),
        ),
    ]
