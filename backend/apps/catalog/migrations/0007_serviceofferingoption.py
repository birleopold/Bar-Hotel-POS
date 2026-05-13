from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_serviceoffering"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceOfferingOption",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "duration_minutes",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Optional duration override for this service package.",
                        null=True,
                    ),
                ),
                (
                    "kds_station",
                    models.CharField(
                        blank=True,
                        help_text="Optional station override; blank uses parent service station.",
                        max_length=32,
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "service_offering",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="options",
                        to="catalog.serviceoffering",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "name"],
                "unique_together": {("service_offering", "name")},
            },
        ),
    ]
