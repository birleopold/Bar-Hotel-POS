import uuid
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0029_order_quick_create_key"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OutletDeliverySettings",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("is_enabled", models.BooleanField(default=False)),
                ("outlet", models.OneToOneField(
                    to="tenants.outlet", on_delete=django.db.models.deletion.CASCADE,
                    related_name="delivery_settings",
                )),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE,
                    related_name="delivery_settings",
                )),
            ],
            options={"ordering": ["outlet"]},
        ),
        migrations.CreateModel(
            name="OrderDelivery",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("status", models.CharField(max_length=16, default="requested", choices=[
                    ("requested", "Requested"), ("accepted", "Accepted"),
                    ("preparing", "Preparing"), ("ready", "Ready to dispatch"),
                    ("dispatched", "Dispatched"), ("delivered", "Delivered"),
                    ("failed", "Failed attempt"), ("returned", "Returned"),
                    ("cancelled", "Cancelled"),
                ])),
                ("destination_type", models.CharField(max_length=16, choices=[
                    ("address", "External address"), ("room", "Hotel guest room"),
                ])),
                ("recipient_name", models.CharField(max_length=120, blank=True)),
                ("contact_phone", models.CharField(max_length=40, blank=True)),
                ("address", models.CharField(max_length=500, blank=True)),
                ("room_reference", models.CharField(max_length=64, blank=True)),
                ("instructions", models.CharField(max_length=500, blank=True)),
                ("promised_at", models.DateTimeField(null=True, blank=True)),
                ("fee", models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))),
                ("currency", models.CharField(max_length=3)),
                ("dispatched_at", models.DateTimeField(null=True, blank=True)),
                ("delivered_at", models.DateTimeField(null=True, blank=True)),
                ("delivery_note", models.CharField(max_length=500, blank=True)),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE,
                    related_name="order_deliveries",
                )),
                ("outlet", models.ForeignKey(
                    to="tenants.outlet", on_delete=django.db.models.deletion.PROTECT,
                    related_name="order_deliveries",
                )),
                ("order", models.OneToOneField(
                    to="pos.order", on_delete=django.db.models.deletion.PROTECT,
                    related_name="delivery",
                )),
                ("assigned_driver", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True, related_name="assigned_deliveries",
                )),
                ("created_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL,
                    null=True, related_name="created_deliveries",
                )),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(
                    fields=["tenant", "outlet", "status"], name="pos_delivery_queue_idx",
                )],
            },
        ),
    ]
