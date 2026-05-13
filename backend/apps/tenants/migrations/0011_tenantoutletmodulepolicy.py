from django.db import migrations, models
import django.db.models.deletion
import apps.tenants.models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0010_billing_invoice_and_events"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantOutletModulePolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "outlet_type",
                    models.CharField(
                        choices=[
                            ("restaurant", "Restaurant"),
                            ("bar", "Bar"),
                            ("lounge", "Lounge"),
                            ("cafeteria", "Cafeteria"),
                            ("lodging_front_desk", "Lodging / front desk"),
                            ("retail", "Retail / shop"),
                            ("supermarket", "Supermarket / grocery"),
                            ("event_space", "Event space"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "enabled_modules",
                    models.JSONField(
                        default=apps.tenants.models.default_enabled_staff_modules,
                        help_text="Module keys enabled for this outlet type in this tenant.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outlet_module_policies",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["tenant__name", "outlet_type"],
                "unique_together": {("tenant", "outlet_type")},
            },
        ),
    ]
