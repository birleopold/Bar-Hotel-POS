from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0018_business_date_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="tenantsetupprogress", name="practice_sale_checked_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="tenantsetupprogress", name="practice_sale_checked_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                related_name="practice_sale_checks",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
            ),
        ),
    ]
