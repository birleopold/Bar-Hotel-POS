from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_supermarketskuprofile"),
        ("tenants", "0012_tenantsettings_hardware_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceOffering",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "default_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "tax_rate_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="If set, tax is computed on service subtotal (exclusive).",
                        max_digits=5,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                (
                    "duration_minutes",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Optional expected duration for scheduling visibility.",
                        null=True,
                    ),
                ),
                (
                    "kds_station",
                    models.CharField(
                        blank=True,
                        default="service",
                        help_text="Prep/ops station tag (e.g. service, sauna, spa, bar).",
                        max_length=32,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_offerings",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "outlets",
                    models.ManyToManyField(
                        blank=True,
                        help_text="If empty, service is available at every outlet of the tenant.",
                        related_name="service_offerings",
                        to="tenants.outlet",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("tenant", "name")},
            },
        ),
    ]
