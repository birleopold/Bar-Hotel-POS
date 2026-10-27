import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0045_workstation_device_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkstationBridgeCredential",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("label", models.CharField(max_length=80)),
                ("token_hash", models.CharField(editable=False, max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revocation_reason", models.CharField(blank=True, max_length=255)),
                (
                    "approved_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workstation_bridges_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workstation_bridges_revoked",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workstation_bridge_credentials",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "workstation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bridge_credentials",
                        to="pos.workstation",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="WorkstationDeviceCommand",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "command_type",
                    models.CharField(
                        choices=[
                            ("ping", "Ping device"),
                            ("print_receipt", "Print receipt"),
                            ("print_kitchen", "Print kitchen ticket"),
                            ("open_drawer", "Open cash drawer"),
                            ("read_scale", "Read scale"),
                        ],
                        max_length=24,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=128)),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("claimed", "Claimed"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("expired", "Expired"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=3)),
                ("not_before", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField()),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error", models.CharField(blank=True, max_length=500)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workstation_device_commands_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="commands",
                        to="pos.workstationdevice",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workstation_device_commands",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "workstation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="device_commands",
                        to="pos.workstation",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="workstationdevicecommand",
            constraint=models.UniqueConstraint(
                fields=("tenant", "idempotency_key"),
                name="uniq_device_command_idempotency_per_tenant",
            ),
        ),
    ]
