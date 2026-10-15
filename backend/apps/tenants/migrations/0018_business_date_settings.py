from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("tenants", "0017_tenantdomain")]

    operations = [
        migrations.AddField(
            model_name="tenantsettings", name="business_day_cutover_hour",
            field=models.PositiveSmallIntegerField(
                default=4,
                validators=[django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(23)],
                help_text="Local hour at which the next operating day begins (0–23).",
            ),
        ),
        migrations.AddField(
            model_name="site", name="business_timezone",
            field=models.CharField(
                blank=True, max_length=64,
                help_text="Optional property timezone; blank uses the business default.",
            ),
        ),
        migrations.AddField(
            model_name="site", name="business_day_cutover_hour",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(23)],
                help_text="Optional property closing boundary; blank uses the business default.",
            ),
        ),
    ]
