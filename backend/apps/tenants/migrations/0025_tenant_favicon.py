from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tenants", "0024_tenant_login_appearance")]

    operations = [
        migrations.AddField(
            model_name="tenantsettings",
            name="favicon_url",
            field=models.URLField(blank=True, help_text="Optional HTTPS square icon for browser tabs; defaults to business logo."),
        ),
    ]
