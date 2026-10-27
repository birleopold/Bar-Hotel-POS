import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_attendance_shift_break"),
        ("catalog", "0032_promotion_recurring_schedule"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommissionRule",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=80)),
                ("rate_percent", models.DecimalField(decimal_places=2, max_digits=5)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="commission_rules", to="catalog.menucategory")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="commission_rules_created", to=settings.AUTH_USER_MODEL)),
                ("membership", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="commission_rules", to="accounts.membership")),
                ("menu_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="commission_rules", to="catalog.menuitem")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commission_rules", to="tenants.tenant")),
            ],
            options={"ordering": ["-is_active", "name"]},
        ),
        migrations.CreateModel(
            name="SalesTarget",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("target_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_targets_created", to=settings.AUTH_USER_MODEL)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_targets", to="accounts.membership")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_targets", to="tenants.tenant")),
            ],
            options={"ordering": ["-period_start", "membership"]},
        ),
        migrations.AddConstraint(
            model_name="commissionrule",
            constraint=models.UniqueConstraint(fields=("tenant", "name"), name="uniq_commission_rule_name_per_tenant"),
        ),
        migrations.AddConstraint(
            model_name="commissionrule",
            constraint=models.CheckConstraint(condition=models.Q(("rate_percent__gte", 0), ("rate_percent__lte", 100)), name="commission_rate_percent_0_100"),
        ),
        migrations.AddConstraint(
            model_name="salestarget",
            constraint=models.CheckConstraint(condition=models.Q(("target_amount__gte", 0)), name="sales_target_amount_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="salestarget",
            constraint=models.UniqueConstraint(fields=("tenant", "membership", "period_start", "period_end"), name="uniq_sales_target_worker_period"),
        ),
    ]
