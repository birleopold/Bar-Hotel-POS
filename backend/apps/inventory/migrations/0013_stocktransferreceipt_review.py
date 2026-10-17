from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0012_stocktransferreceipt_rls"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="stocktransferreceipt", name="review_action",
            field=models.CharField(max_length=20, blank=True, default="", choices=[
                ("", "Not reviewed"),
                ("needs_count", "Physical recount required"),
                ("documented", "Investigation documented"),
            ]),
        ),
        migrations.AddField(
            model_name="stocktransferreceipt", name="review_note",
            field=models.CharField(max_length=512, blank=True),
        ),
        migrations.AddField(
            model_name="stocktransferreceipt", name="reviewed_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="stocktransferreceipt", name="reviewed_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL, null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_transfer_discrepancies",
            ),
        ),
    ]
