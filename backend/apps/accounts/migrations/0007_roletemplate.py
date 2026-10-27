import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_passwordrecoveryrequest"),
        ("tenants", "0008_tenantsetupprogress_step_state_overrides"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleTemplate",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=80)),
                ("description", models.CharField(blank=True, max_length=255)),
                (
                    "base_role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("tenant_admin", "Tenant admin"),
                            ("site_manager", "Site manager"),
                            ("outlet_manager", "Outlet manager"),
                            ("front_desk", "Front desk"),
                            ("server", "Server / floor"),
                            ("bartender", "Bartender"),
                            ("kitchen", "Kitchen"),
                            ("storekeeper", "Storekeeper"),
                            ("accountant", "Accountant (read-only)"),
                            ("cleaner", "Housekeeping"),
                        ],
                        max_length=32,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="role_templates_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_templates",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "outlets",
                    models.ManyToManyField(
                        blank=True,
                        related_name="role_templates",
                        to="tenants.outlet",
                    ),
                ),
                (
                    "sites",
                    models.ManyToManyField(
                        blank=True,
                        related_name="role_templates",
                        to="tenants.site",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="roletemplate",
            constraint=models.UniqueConstraint(
                fields=("tenant", "name"),
                name="uniq_role_template_name_per_tenant",
            ),
        ),
    ]
