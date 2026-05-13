from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0007_tenantsetupprogress"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantsetupprogress",
            name="step_state_overrides",
            field=models.JSONField(
                default=dict,
                help_text="Optional per-step manual states (e.g. skipped, blocked).",
            ),
        ),
    ]
