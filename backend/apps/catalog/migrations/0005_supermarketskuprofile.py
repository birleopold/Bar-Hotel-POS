from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0010_billing_invoice_and_events"),
        ("catalog", "0004_menuitem_consume_recipe_on_sale_menuitem_kds_station_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupermarketSkuProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("department", models.CharField(blank=True, max_length=64)),
                (
                    "barcode_mode",
                    models.CharField(
                        choices=[("scan", "Scanned barcode"), ("plu", "PLU code")],
                        default="scan",
                        max_length=16,
                    ),
                ),
                ("plu_code", models.CharField(blank=True, max_length=16)),
                (
                    "weighted_pricing_mode",
                    models.CharField(
                        choices=[("unit", "Unit priced"), ("weighted", "Weighted at checkout")],
                        default="unit",
                        max_length=16,
                    ),
                ),
                ("allow_fractional_quantity", models.BooleanField(default=False)),
                (
                    "sell_by_unit",
                    models.BooleanField(
                        default=True,
                        help_text="When false and weighted mode is active, checkout expects measured quantity.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "menu_item",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supermarket_profile",
                        to="catalog.menuitem",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supermarket_skus",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["tenant__name", "menu_item__name"],
                "unique_together": {("tenant", "plu_code")},
            },
        ),
    ]
