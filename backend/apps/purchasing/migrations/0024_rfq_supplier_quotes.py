import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models.functions import Lower
import django.db.models.deletion


RFQ_TABLES = [
    "purchasing_purchaserfq",
    "purchasing_purchaserfqline",
    "purchasing_supplierquote",
    "purchasing_supplierquoteline",
]


def enable_rfq_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in RFQ_TABLES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(
                f'''CREATE POLICY tenant_isolation ON "{table}" FOR ALL USING (
                    tenant_id::text = current_setting('app.tenant_id', true)
                )'''
            )


def disable_rfq_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in reversed(RFQ_TABLES):
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0023_purchase_order_approval"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseRfq",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(max_length=128)),
                ("status", models.CharField(
                    choices=[
                        ("draft", "Draft"),
                        ("open", "Open for quotations"),
                        ("awarded", "Awarded"),
                        ("cancelled", "Cancelled"),
                    ],
                    default="draft", max_length=16,
                )),
                ("needed_by", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="purchase_rfqs_created",
                    to="accounts.user",
                )),
                ("outlet", models.ForeignKey(
                    help_text="Outlet/warehouse that will receive the awarded purchase order.",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="purchase_rfqs",
                    to="tenants.outlet",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="purchase_rfqs",
                    to="tenants.tenant",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="purchaserfq",
            constraint=models.UniqueConstraint(
                Lower("reference"), "tenant",
                name="uniq_purchase_rfq_reference_ci",
            ),
        ),
        migrations.CreateModel(
            name="PurchaseRfqLine",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quantity_requested", models.DecimalField(
                    decimal_places=3, max_digits=14,
                    validators=[MinValueValidator(Decimal("0.001"))],
                )),
                ("note", models.CharField(blank=True, max_length=255)),
                ("menu_item", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="purchase_rfq_lines",
                    to="catalog.menuitem",
                )),
                ("rfq", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lines",
                    to="purchasing.purchaserfq",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="purchase_rfq_lines",
                    to="tenants.tenant",
                )),
            ],
            options={"ordering": ["rfq", "menu_item__name"]},
        ),
        migrations.AddConstraint(
            model_name="purchaserfqline",
            constraint=models.UniqueConstraint(
                fields=("rfq", "menu_item"),
                name="uniq_purchase_rfq_item",
            ),
        ),
        migrations.CreateModel(
            name="SupplierQuote",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(
                    choices=[
                        ("invited", "Invited / awaiting quote"),
                        ("submitted", "Quote received"),
                        ("accepted", "Accepted"),
                        ("rejected", "Not selected"),
                    ],
                    default="invited", max_length=16,
                )),
                ("reference", models.CharField(
                    blank=True,
                    help_text="Supplier quotation/reference number.",
                    max_length=128,
                )),
                ("shipping_cost", models.DecimalField(
                    decimal_places=2, default=Decimal("0"), max_digits=14,
                    validators=[MinValueValidator(Decimal("0"))],
                )),
                ("other_cost", models.DecimalField(
                    decimal_places=2, default=Decimal("0"),
                    help_text="Other quoted charges not included in item unit prices.",
                    max_digits=14,
                    validators=[MinValueValidator(Decimal("0"))],
                )),
                ("lead_time_days", models.PositiveIntegerField(blank=True, null=True)),
                ("availability_note", models.CharField(blank=True, max_length=255)),
                ("payment_terms", models.CharField(blank=True, max_length=255)),
                ("valid_until", models.DateField(blank=True, null=True)),
                ("converted_purchase_order", models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="source_supplier_quote",
                    to="purchasing.purchaseorder",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="supplier_quotes_recorded",
                    to="accounts.user",
                )),
                ("rfq", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="quotes",
                    to="purchasing.purchaserfq",
                )),
                ("supplier", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="quotes",
                    to="purchasing.supplier",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="supplier_quotes",
                    to="tenants.tenant",
                )),
            ],
            options={"ordering": ["rfq", "supplier__name"]},
        ),
        migrations.AddConstraint(
            model_name="supplierquote",
            constraint=models.UniqueConstraint(
                fields=("rfq", "supplier"),
                name="uniq_supplier_quote_per_rfq",
            ),
        ),
        migrations.AddConstraint(
            model_name="supplierquote",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "accepted")),
                fields=("rfq",),
                name="uniq_accepted_quote_per_rfq",
            ),
        ),
        migrations.CreateModel(
            name="SupplierQuoteLine",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("unit_cost", models.DecimalField(
                    decimal_places=2, max_digits=12,
                    validators=[MinValueValidator(Decimal("0"))],
                )),
                ("quantity_available", models.DecimalField(
                    blank=True, decimal_places=3,
                    help_text="Blank means supplier did not state an availability limit.",
                    max_digits=14, null=True,
                    validators=[MinValueValidator(Decimal("0"))],
                )),
                ("promised_date", models.DateField(blank=True, null=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("quote", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lines",
                    to="purchasing.supplierquote",
                )),
                ("rfq_line", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="quote_lines",
                    to="purchasing.purchaserfqline",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="supplier_quote_lines",
                    to="tenants.tenant",
                )),
            ],
            options={"ordering": ["quote", "rfq_line__menu_item__name"]},
        ),
        migrations.AddConstraint(
            model_name="supplierquoteline",
            constraint=models.UniqueConstraint(
                fields=("quote", "rfq_line"),
                name="uniq_supplier_quote_rfq_line",
            ),
        ),
        migrations.RunPython(enable_rfq_rls, disable_rfq_rls),
    ]
