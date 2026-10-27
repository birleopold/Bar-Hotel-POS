import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0015_retail_assembly_component"),
        ("inventory", "0016_stock_shelf_location_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="RetailAssemblyRun",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("direction", models.CharField(choices=[("build", "Build"), ("unbuild", "Unbuild")], max_length=16)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=14, validators=[MinValueValidator(Decimal("0.001"))])),
                ("note", models.CharField(blank=True, max_length=512)),
                ("assembled_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="retail_assembly_runs", to="catalog.menuitem")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="retail_assembly_runs_created", to="accounts.user")),
                ("outlet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="retail_assembly_runs", to="tenants.outlet")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="retail_assembly_runs", to="tenants.tenant")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="assembly_run",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_movements", to="inventory.retailassemblyrun"),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="reason",
            field=models.CharField(choices=[
                ("receive", "Receive / purchase"),
                ("sale", "Sale (POS)"),
                ("adjust_in", "Adjustment increase"),
                ("adjust_out", "Adjustment decrease"),
                ("waste", "Waste / shrink"),
                ("transfer_out", "Transfer out"),
                ("transfer_in", "Transfer in"),
                ("physical_count", "Physical count adjustment"),
                ("recipe", "Recipe / BOM consumption"),
                ("assembly_build", "Assembly build"),
                ("assembly_unbuild", "Assembly unbuild"),
            ], max_length=16),
        ),
    ]
