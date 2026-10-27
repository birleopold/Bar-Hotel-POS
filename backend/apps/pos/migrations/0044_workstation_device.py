import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0043_orderline_commission_settled_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkstationDevice",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "device_type",
                    models.CharField(
                        choices=[
                            ("receipt_printer", "Receipt printer"),
                            ("kitchen_printer", "Kitchen printer"),
                            ("cash_drawer", "Cash drawer"),
                            ("barcode_scanner", "Barcode scanner"),
                            ("weighing_scale", "Weighing scale"),
                            ("customer_display", "Customer display"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "adapter",
                    models.CharField(
                        choices=[
                            ("browser_print", "Browser print dialog"),
                            ("keyboard_wedge", "Keyboard-wedge input"),
                            ("paired_browser", "Paired browser display"),
                            ("local_bridge", "Local hardware bridge"),
                            ("manual", "Manual / external device"),
                        ],
                        max_length=24,
                    ),
                ),
                ("label", models.CharField(max_length=120)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "health_status",
                    models.CharField(
                        choices=[
                            ("unknown", "Unknown"),
                            ("online", "Online"),
                            ("degraded", "Degraded"),
                            ("offline", "Offline"),
                        ],
                        default="unknown",
                        max_length=16,
                    ),
                ),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("consecutive_failures", models.PositiveSmallIntegerField(default=0)),
                ("last_latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workstation_devices_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workstation_devices",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "workstation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="devices",
                        to="pos.workstation",
                    ),
                ),
            ],
            options={"ordering": ["workstation", "device_type", "label"]},
        ),
        migrations.AddConstraint(
            model_name="workstationdevice",
            constraint=models.UniqueConstraint(
                fields=("workstation", "device_type", "label"),
                name="uniq_workstation_device_label_type",
            ),
        ),
    ]
