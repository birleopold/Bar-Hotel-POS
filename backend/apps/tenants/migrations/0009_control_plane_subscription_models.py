from django.db import migrations, models
import django.db.models.deletion
import apps.tenants.models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0008_tenantsetupprogress_step_state_overrides"),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("code", models.SlugField(max_length=80, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("monthly_price", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                (
                    "included_modules",
                    models.JSONField(
                        default=apps.tenants.models.default_plan_included_modules,
                        help_text="Staff module keys enabled by default on this plan.",
                    ),
                ),
                ("notes", models.TextField(blank=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TenantFeatureEntitlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("module_key", models.CharField(max_length=32)),
                ("is_enabled", models.BooleanField(default=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_entitlements",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["tenant__name", "module_key"],
                "unique_together": {("tenant", "module_key")},
            },
        ),
        migrations.CreateModel(
            name="TenantSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("trial", "Trial"),
                            ("active", "Active"),
                            ("past_due", "Past due"),
                            ("suspended", "Suspended"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="trial",
                        max_length=16,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("trial_ends_at", models.DateTimeField(blank=True, null=True)),
                ("current_period_ends_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="tenants.plan",
                    ),
                ),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscription",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={"ordering": ["tenant__name"]},
        ),
    ]
