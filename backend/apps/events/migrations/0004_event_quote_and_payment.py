import uuid
from django.db import migrations, models
import django.core.validators
from decimal import Decimal
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("events", "0003_eventbooking_customer")]

    operations = [
        migrations.CreateModel(
            name="EventQuote",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(max_length=128)),
                ("amount", models.DecimalField(max_digits=14, decimal_places=2, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ("description", models.TextField(blank=True)),
                ("valid_until", models.DateField()),
                ("status", models.CharField(max_length=16, default="draft", choices=[("draft", "Draft"), ("sent", "Sent"), ("accepted", "Accepted")])),
                ("accepted_at", models.DateTimeField(null=True, blank=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant", related_name="event_quotes", on_delete=django.db.models.deletion.CASCADE)),
                ("booking", models.ForeignKey(to="events.eventbooking", related_name="quotes", on_delete=django.db.models.deletion.PROTECT)),
                ("created_by", models.ForeignKey(to="accounts.user", related_name="event_quotes_created", on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True)),
            ],
            options={"ordering": ["-created_at"], "constraints": [
                models.UniqueConstraint(fields=("tenant", "booking", "reference"), name="uniq_event_quote_number_booking"),
            ]},
        ),
        migrations.CreateModel(
            name="EventPayment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount", models.DecimalField(max_digits=14, decimal_places=2, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ("method", models.CharField(max_length=16, choices=[
                    ("cash", "Cash"), ("card", "Card"), ("mobile_money", "Mobile money"),
                    ("bank", "Bank transfer"), ("other", "Other"),
                ])),
                ("reference", models.CharField(max_length=128, blank=True)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("tenant", models.ForeignKey(to="tenants.tenant", related_name="event_payments", on_delete=django.db.models.deletion.CASCADE)),
                ("booking", models.ForeignKey(to="events.eventbooking", related_name="payments", on_delete=django.db.models.deletion.PROTECT)),
                ("recorded_by", models.ForeignKey(to="accounts.user", related_name="event_payments_recorded", on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True)),
            ],
            options={"ordering": ["-created_at"], "constraints": [
                models.UniqueConstraint(fields=("tenant", "idempotency_key"), name="uniq_event_payment_key_tenant"),
            ]},
        ),
    ]
