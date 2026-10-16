import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0002_customer_rls"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LoyaltyLedgerEntry",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("points", models.IntegerField()),
                ("source_type", models.CharField(max_length=24, choices=[
                    ("adjustment", "Manager adjustment"), ("sale", "Sale reward"),
                    ("refund", "Refund reversal"), ("redemption", "Reward redemption"),
                ])),
                ("source_key", models.CharField(max_length=128)),
                ("reason", models.CharField(max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE, related_name="loyalty_entries")),
                ("customer", models.ForeignKey(to="customers.customer", on_delete=django.db.models.deletion.PROTECT, related_name="loyalty_entries")),
                ("recorded_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True)),
            ],
            options={"ordering": ["-created_at", "-pk"], "constraints": [
                models.UniqueConstraint(fields=("tenant", "source_type", "source_key"), name="uniq_loyalty_source"),
                models.CheckConstraint(condition=~models.Q(points=0), name="nonzero_loyalty_points"),
            ]},
        ),
    ]
