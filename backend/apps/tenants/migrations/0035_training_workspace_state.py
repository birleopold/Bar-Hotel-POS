import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0034_tenant_is_training"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainingWorkspaceState",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("generation", models.PositiveIntegerField(default=0)),
                ("seeded_at", models.DateTimeField(blank=True, null=True)),
                ("sample_ids", models.JSONField(blank=True, default=dict)),
                ("exercise_progress", models.JSONField(blank=True, default=dict)),
                (
                    "seeded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="training_workspaces_seeded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="training_state",
                        to="tenants.tenant",
                    ),
                ),
            ],
        ),
    ]
