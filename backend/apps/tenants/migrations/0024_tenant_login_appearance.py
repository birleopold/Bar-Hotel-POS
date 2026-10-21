from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tenants", "0023_offline_cash_payment_limit")]

    operations = [
        migrations.AddField(
            model_name="tenantsettings",
            name="login_background_url",
            field=models.URLField(blank=True, help_text="Optional HTTPS image for your branded staff login background."),
        ),
        migrations.AddField(
            model_name="tenantsettings",
            name="login_welcome_message",
            field=models.CharField(blank=True, max_length=160, help_text="Optional greeting displayed on staff sign-in screens."),
        ),
    ]
