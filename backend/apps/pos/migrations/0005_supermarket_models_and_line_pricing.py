import django.core.validators
from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0004_order_applied_promotion_orderline_kds_station_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="line_discount_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=14,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="orderline",
            name="line_discount_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="orderline",
            name="pricing_source",
            field=models.CharField(
                default="menu",
                help_text="Price source marker (menu, barcode, plu, weighted, manual).",
                max_length=24,
            ),
        ),
        migrations.CreateModel(
            name="PosShift",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], default="open", max_length=16)),
                ("opening_cash", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("expected_cash", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("counted_cash", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("closed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_shifts_closed", to="accounts.user")),
                ("opened_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pos_shifts_opened", to="accounts.user")),
                ("outlet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pos_shifts", to="tenants.outlet")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pos_shifts", to="tenants.tenant")),
            ],
            options={
                "ordering": ["-opened_at"],
            },
        ),
        migrations.CreateModel(
            name="SupermarketLineReturn",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.001"))])),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("restocked", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supermarket_returns_created", to="accounts.user")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supermarket_returns", to="pos.order")),
                ("order_line", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supermarket_returns", to="pos.orderline")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supermarket_returns", to="tenants.tenant")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
