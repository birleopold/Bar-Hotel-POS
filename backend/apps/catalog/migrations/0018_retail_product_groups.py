import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0017_serialized_item_constraint"),
    ]

    operations = [
        migrations.CreateModel(
            name="RetailProductGroup",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("code", models.CharField(blank=True, help_text="Optional cashier lookup code for this group. It does not replace component barcodes.", max_length=64)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="retail_product_groups", to="tenants.tenant")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="RetailProductGroupLine",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=14, validators=[MinValueValidator(Decimal("0.001"))])),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="catalog.retailproductgroup")),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="retail_group_lines", to="catalog.menuitem")),
            ],
            options={"ordering": ["sort_order", "menu_item__name"]},
        ),
        migrations.AddConstraint(
            model_name="retailproductgroup",
            constraint=models.UniqueConstraint(fields=("tenant", "name"), name="uniq_retail_group_name_tenant"),
        ),
        migrations.AddConstraint(
            model_name="retailproductgroup",
            constraint=models.UniqueConstraint(condition=~models.Q(("code", "")), fields=("tenant", "code"), name="uniq_retail_group_code_tenant"),
        ),
        migrations.AddConstraint(
            model_name="retailproductgroupline",
            constraint=models.UniqueConstraint(fields=("group", "menu_item"), name="uniq_retail_group_component"),
        ),
    ]
