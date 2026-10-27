import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0022_product_label_queue"),
        ("customers", "0004_loyalty_rls"),
        ("pos", "0034_orderline_seat_number"),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceBook",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("code", models.CharField(max_length=48)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("outlets", models.ManyToManyField(blank=True, help_text="Empty means every retail outlet in this business.", related_name="price_books", to="tenants.outlet")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="price_books", to="tenants.tenant")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="PriceBookRule",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("minimum_quantity", models.DecimalField(decimal_places=3, default=Decimal("1.000"), max_digits=10, validators=[MinValueValidator(Decimal("0.001"))])),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12, validators=[MinValueValidator(Decimal("0"))])),
                ("is_active", models.BooleanField(default=True)),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="price_book_rules", to="catalog.menuitem")),
                ("price_book", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rules", to="pos.pricebook")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="price_book_rules", to="tenants.tenant")),
            ],
            options={"ordering": ["price_book", "menu_item", "-minimum_quantity"]},
        ),
        migrations.CreateModel(
            name="CustomerPriceBookAssignment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("assigned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="price_book_assignments_made", to="accounts.user")),
                ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="price_book_assignment", to="customers.customer")),
                ("price_book", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="customer_assignments", to="pos.pricebook")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="customer_price_book_assignments", to="tenants.tenant")),
            ],
            options={"ordering": ["customer__name"]},
        ),
        migrations.AddField(
            model_name="orderline",
            name="price_book_base_unit_price",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Original unit price before customer price-book override.", max_digits=12, null=True, validators=[MinValueValidator(Decimal("0"))]),
        ),
        migrations.AddField(
            model_name="orderline",
            name="price_book_rule",
            field=models.ForeignKey(blank=True, help_text="Applied customer price-book rule, if any.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="order_lines", to="pos.pricebookrule"),
        ),
        migrations.AddConstraint(
            model_name="pricebook",
            constraint=models.UniqueConstraint(fields=("tenant", "code"), name="uniq_price_book_code_tenant"),
        ),
        migrations.AddConstraint(
            model_name="pricebook",
            constraint=models.UniqueConstraint(fields=("tenant", "name"), name="uniq_price_book_name_tenant"),
        ),
        migrations.AddConstraint(
            model_name="pricebookrule",
            constraint=models.UniqueConstraint(fields=("price_book", "menu_item", "minimum_quantity"), name="uniq_price_book_item_tier"),
        ),
        migrations.AddConstraint(
            model_name="customerpricebookassignment",
            constraint=models.UniqueConstraint(fields=("tenant", "customer"), name="uniq_customer_price_book_tenant"),
        ),
    ]
