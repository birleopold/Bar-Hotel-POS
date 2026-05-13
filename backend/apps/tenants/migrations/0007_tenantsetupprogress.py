from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0006_alter_tenantsettings_enabled_staff_modules"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantSetupProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("suppress_dashboard_prompt", models.BooleanField(default=False)),
                ("last_completion_percent", models.PositiveSmallIntegerField(default=0)),
                ("last_next_step_key", models.CharField(blank=True, max_length=64)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="setup_progress",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["tenant__name"],
            },
        ),
    ]
