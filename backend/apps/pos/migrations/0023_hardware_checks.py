import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0022_offline_review"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="WorkstationHardwareCheck",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                        editable=False, serialize=False)),
                ("test_type", models.CharField(max_length=20, choices=[
                    ("receipt_printer", "Receipt printer"),
                    ("barcode_scanner", "Barcode scanner"),
                    ("kitchen_display", "Kitchen printer or display"),
                    ("cash_drawer", "Cash drawer"),
                    ("weighing_scale", "Weighing scale"),
                ])),
                ("result", models.CharField(max_length=12, choices=[
                    ("pass", "Observed working"), ("fail", "Observed failure"),
                    ("not_tested", "Not tested"),
                ])),
                ("note", models.CharField(blank=True, max_length=500)),
                ("configured_device", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE,
                    related_name="hardware_checks",
                )),
                ("workstation", models.ForeignKey(
                    to="pos.workstation", on_delete=django.db.models.deletion.PROTECT,
                    related_name="hardware_checks",
                )),
                ("checked_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True, related_name="hardware_checks",
                )),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
    ]
