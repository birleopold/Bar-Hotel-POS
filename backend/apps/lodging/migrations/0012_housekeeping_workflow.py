import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("lodging", "0011_propertynightaudit_rls"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="room", name="assigned_housekeeper",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL, null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="housekeeping_rooms",
            ),
        ),
        migrations.AddField(
            model_name="room", name="housekeeping_started_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="room", name="housekeeping_finished_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="room", name="housekeeping_inspected_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name="room", name="status",
            field=models.CharField(
                max_length=20, default="clean",
                choices=[
                    ("clean", "Clean"), ("dirty", "Dirty"),
                    ("cleaning", "Cleaning"), ("inspected", "Inspected"),
                    ("out_of_order", "Out of order"),
                ],
            ),
        ),
        migrations.CreateModel(
            name="RoomHousekeepingEvent",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False, serialize=False)),
                ("action", models.CharField(max_length=24)),
                ("previous_status", models.CharField(max_length=20)),
                ("new_status", models.CharField(max_length=20)),
                ("previous_assignee_id", models.UUIDField(blank=True, null=True)),
                ("new_assignee_id", models.UUIDField(blank=True, null=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="room_housekeeping_events", to="tenants.tenant")),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="housekeeping_events", to="lodging.room")),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="room_housekeeping_actions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
