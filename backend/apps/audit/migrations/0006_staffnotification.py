import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0005_review_scope_backfill"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffNotification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_type", models.CharField(max_length=32)),
                ("source_id", models.CharField(max_length=128)),
                ("priority", models.CharField(
                    max_length=10, default="normal",
                    choices=[("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")],
                )),
                ("title", models.CharField(max_length=160)),
                ("body", models.CharField(blank=True, max_length=400)),
                ("url", models.CharField(blank=True, max_length=300)),
                ("active", models.BooleanField(default=True)),
                ("read_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="staff_notifications", to="tenants.tenant",
                )),
                ("recipient", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="staff_notifications", to="accounts.membership",
                )),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant", "recipient", "source_type", "source_id"),
                        name="uniq_staff_alert_recipient_source",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["tenant", "recipient", "active", "read_at"],
                        name="staff_alert_inbox_idx",
                    ),
                ],
            },
        ),
    ]
