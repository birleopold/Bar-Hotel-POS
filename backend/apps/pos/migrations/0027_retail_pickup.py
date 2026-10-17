import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0026_wholesale_price_rls"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="RetailPickup", fields=[
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("expected_on", models.DateField()),
            ("status", models.CharField(max_length=16, choices=[("awaiting", "Awaiting customer"), ("collected", "Collected")], default="awaiting")),
            ("note", models.CharField(max_length=300, blank=True)),
            ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE, related_name="retail_pickups")),
            ("order", models.OneToOneField(to="pos.order", on_delete=django.db.models.deletion.PROTECT, related_name="retail_pickup")),
            ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, related_name="retail_pickups_created")),
            ("collected_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="retail_pickups_collected")),
            ("collected_at", models.DateTimeField(null=True, blank=True)),
        ], options={"ordering":["expected_on","created_at"]}),
    ]
