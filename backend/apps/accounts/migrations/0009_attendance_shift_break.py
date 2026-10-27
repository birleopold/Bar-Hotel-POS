import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_membership_role_template"),
        ("tenants", "0008_tenantsetupprogress_step_state_overrides"),
    ]

    operations = [
        migrations.CreateModel(
            name="AttendanceShift",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Clocked in"),
                            ("pending", "Pending review"),
                            ("approved", "Approved"),
                        ],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("clock_in_at", models.DateTimeField()),
                ("clock_out_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_note", models.CharField(blank=True, max_length=500)),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="attendance_shifts",
                        to="accounts.membership",
                    ),
                ),
                (
                    "outlet",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="attendance_shifts",
                        to="tenants.outlet",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="attendance_shifts_reviewed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="attendance_shifts",
                        to="tenants.site",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_shifts",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={"ordering": ["-clock_in_at"]},
        ),
        migrations.CreateModel(
            name="AttendanceBreak",
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
                ("started_at", models.DateTimeField()),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("is_paid", models.BooleanField(default=False)),
                ("note", models.CharField(blank=True, max_length=255)),
                (
                    "shift",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="breaks",
                        to="accounts.attendanceshift",
                    ),
                ),
            ],
            options={"ordering": ["started_at"]},
        ),
        migrations.AddConstraint(
            model_name="attendanceshift",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "open")),
                fields=("membership",),
                name="uniq_open_attendance_shift_per_membership",
            ),
        ),
        migrations.AddConstraint(
            model_name="attendancebreak",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ended_at__isnull", True)),
                fields=("shift",),
                name="uniq_open_attendance_break_per_shift",
            ),
        ),
    ]
