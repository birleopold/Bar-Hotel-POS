import uuid
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0019_practice_sale_setup"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="OwnerReportSchedule",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_enabled", models.BooleanField(default=False)),
                ("frequency", models.CharField(max_length=8, default="daily", choices=[
                    ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly"),
                ])),
                ("local_send_hour", models.PositiveSmallIntegerField(
                    default=8, validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(23),
                    ],
                )),
                ("send_weekday", models.PositiveSmallIntegerField(
                    default=0, help_text="Monday=0 through Sunday=6.", validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(6),
                    ],
                )),
                ("send_monthday", models.PositiveSmallIntegerField(
                    default=1, help_text="Use days 1–28, supported in all calendar months.", validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(28),
                    ],
                )),
                ("tenant", models.OneToOneField(
                    to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE,
                    related_name="owner_report_schedule",
                )),
                ("site", models.ForeignKey(
                    to="tenants.site", on_delete=django.db.models.deletion.PROTECT,
                    null=True, blank=True, related_name="owner_report_schedules",
                    help_text="Optional single-property operating-date scope. Blank is a UTC-calendar tenant report.",
                )),
                ("recipients", models.ManyToManyField(
                    to="accounts.membership", blank=True,
                    related_name="owner_report_preferences",
                )),
            ],
        ),
        migrations.CreateModel(
            name="OwnerReportDelivery",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("recipient_snapshot", models.JSONField(default=list)),
                ("status", models.CharField(max_length=8, default="sending", choices=[
                    ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed"),
                ])),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_attempt_at", models.DateTimeField(null=True, blank=True)),
                ("sent_at", models.DateTimeField(null=True, blank=True)),
                ("error_message", models.CharField(max_length=300, blank=True)),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE,
                    related_name="owner_report_deliveries",
                )),
                ("schedule", models.ForeignKey(
                    to="tenants.ownerreportschedule",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="deliveries",
                )),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [models.UniqueConstraint(
                    fields=("schedule", "period_start", "period_end"),
                    name="uniq_owner_report_delivery_period",
                )],
            },
        ),
    ]
