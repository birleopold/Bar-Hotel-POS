import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_merge_20261005_2237"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PasswordRecoveryRequest",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("status", models.CharField(max_length=16, default="pending", choices=[("pending", "Pending review"), ("sent", "Approved and emailed"), ("used", "Used"), ("denied", "Denied")])),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("token_digest", models.CharField(max_length=64, blank=True, editable=False)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_recoveries", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recovery_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-requested_at"]},
        ),
        migrations.AddIndex(
            model_name="passwordrecoveryrequest",
            index=models.Index(fields=["user", "status", "requested_at"], name="accounts_pr_user_id_85d14d_idx"),
        ),
    ]
