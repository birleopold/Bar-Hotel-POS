from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0021_kds_ticket_controls"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="offlinequeuedoperation", name="review_note",
            field=models.CharField(max_length=500, blank=True),
        ),
        migrations.AddField(
            model_name="offlinequeuedoperation", name="reviewed_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="offlinequeuedoperation", name="reviewed_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL, null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="offline_reviews",
            ),
        ),
    ]
