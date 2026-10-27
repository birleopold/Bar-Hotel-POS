import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0014_product_variant_matrix"),
    ]

    operations = [
        migrations.CreateModel(
            name="RetailAssemblyComponent",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quantity_per_unit", models.DecimalField(decimal_places=3, help_text="Base stock units of this component required to build one finished unit.", max_digits=14, validators=[MinValueValidator(Decimal("0.001"))])),
                ("component_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="used_in_retail_assemblies", to="catalog.menuitem")),
                ("parent_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assembly_components", to="catalog.menuitem")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="retail_assembly_components", to="tenants.tenant")),
            ],
            options={"ordering": ["parent_item", "component_item__name"]},
        ),
        migrations.AddConstraint(
            model_name="retailassemblycomponent",
            constraint=models.UniqueConstraint(fields=("parent_item", "component_item"), name="uniq_retail_assembly_component"),
        ),
    ]
