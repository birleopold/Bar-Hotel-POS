import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("lodging", "0009_folio_customer_reservation_customer"),
        ("tenants", "0018_business_date_settings"),
    ]
    operations = [
        migrations.CreateModel(
            name="PropertyNightAudit",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(primary_key=True, serialize=False, editable=False, default=uuid.uuid4)),
                ("business_date", models.DateField()),
                ("closed_at", models.DateTimeField(auto_now_add=True)),
                ("note", models.CharField(max_length=512, blank=True)),
                ("snapshot", models.JSONField(default=dict)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="property_night_audits", to="tenants.tenant")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="night_audits", to="tenants.site")),
                ("closed_by", models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, null=True, related_name="property_audits_closed", to="accounts.user")),
            ],
            options={
                "ordering": ["-business_date"],
                "constraints": [
                    models.UniqueConstraint(fields=("site", "business_date"), name="uniq_night_audit_site_date"),
                ],
            },
        ),
    ]
