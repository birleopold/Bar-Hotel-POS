import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models.functions import Lower
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0020_retail_group_line_tenant"),
    ]

    operations = [
        migrations.AddField(
            model_name="menuitem",
            name="brand",
            field=models.CharField(blank=True, help_text="Optional brand or manufacturer name.", max_length=128),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="model_number",
            field=models.CharField(blank=True, help_text="Optional model, style, or manufacturer model number.", max_length=128),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="reference_code",
            field=models.CharField(blank=True, help_text="Optional internal or manufacturer reference code.", max_length=128),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="msrp",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Optional manufacturer suggested retail price; does not override the selling price.", max_digits=12, null=True, validators=[MinValueValidator(Decimal("0"))]),
        ),
        migrations.CreateModel(
            name="ProductCustomFieldDefinition",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=96)),
                ("key", models.SlugField(max_length=96)),
                ("field_type", models.CharField(choices=[("text", "Text"), ("number", "Number"), ("boolean", "Yes / no")], default="text", max_length=16)),
                ("help_text", models.CharField(blank=True, max_length=255)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_custom_field_definitions", to="tenants.tenant")),
            ],
            options={"ordering": ["sort_order", "name"]},
        ),
        migrations.CreateModel(
            name="ProductAlternateCode",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(db_index=True, max_length=128)),
                ("code_type", models.CharField(choices=[("internal", "Internal"), ("supplier", "Supplier"), ("manufacturer", "Manufacturer"), ("other", "Other")], default="internal", max_length=16)),
                ("label", models.CharField(blank=True, max_length=96)),
                ("is_active", models.BooleanField(default=True)),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alternate_codes", to="catalog.menuitem")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_alternate_codes", to="tenants.tenant")),
            ],
            options={"ordering": ["menu_item__name", "code_type", "code"]},
        ),
        migrations.CreateModel(
            name="ProductCustomFieldValue",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("value_text", models.TextField(blank=True)),
                ("definition", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="values", to="catalog.productcustomfielddefinition")),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="custom_field_values", to="catalog.menuitem")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_custom_field_values", to="tenants.tenant")),
            ],
            options={"ordering": ["definition__sort_order", "definition__name"]},
        ),
        migrations.AddConstraint(
            model_name="productcustomfielddefinition",
            constraint=models.UniqueConstraint(fields=("tenant", "key"), name="uniq_product_custom_field_key_tenant"),
        ),
        migrations.AddConstraint(
            model_name="productcustomfielddefinition",
            constraint=models.UniqueConstraint(Lower("name"), "tenant", name="uniq_product_custom_field_name_ci_tenant"),
        ),
        migrations.AddConstraint(
            model_name="productalternatecode",
            constraint=models.UniqueConstraint(Lower("code"), "tenant", name="uniq_product_alternate_code_ci_tenant"),
        ),
        migrations.AddConstraint(
            model_name="productcustomfieldvalue",
            constraint=models.UniqueConstraint(fields=("menu_item", "definition"), name="uniq_product_custom_value_item_definition"),
        ),
    ]
