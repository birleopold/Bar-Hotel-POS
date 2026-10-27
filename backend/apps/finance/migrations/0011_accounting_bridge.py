import uuid
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0010_cashbook_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountingMapping",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[
                    ("revenue_default", "Revenue default"),
                    ("revenue_category", "Revenue category"),
                    ("returns", "Sales returns"),
                    ("tender", "Tender clearing"),
                    ("tax_liability", "Tax / VAT liability"),
                    ("inventory_default", "Inventory asset default"),
                    ("inventory_category", "Inventory asset category"),
                    ("cogs_default", "COGS default"),
                    ("cogs_category", "COGS category"),
                ], max_length=32)),
                ("source_key", models.CharField(blank=True, default="", help_text="Category UUID, tender method, or blank for a default mapping.", max_length=128)),
                ("source_label", models.CharField(blank=True, default="", max_length=128)),
                ("account_code", models.CharField(max_length=64)),
                ("account_name", models.CharField(max_length=128)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accounting_mappings_created", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="accounting_mappings", to="tenants.tenant")),
            ],
            options={"ordering": ["kind", "source_label", "account_code"]},
        ),
        migrations.CreateModel(
            name="AccountingExportBatch",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("date_from", models.DateField()),
                ("date_to", models.DateField()),
                ("currency", models.CharField(max_length=3)),
                ("scope_outlet_ids", models.JSONField(blank=True, default=list)),
                ("mapping_snapshot", models.JSONField(blank=True, default=dict)),
                ("journal_lines", models.JSONField(blank=True, default=list)),
                ("source_summary", models.JSONField(blank=True, default=dict)),
                ("fingerprint", models.CharField(db_index=True, max_length=64)),
                ("line_count", models.PositiveIntegerField(default=0)),
                ("total_debit", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=16)),
                ("total_credit", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=16)),
                ("generated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accounting_exports_generated", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="accounting_export_batches", to="tenants.tenant")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="accountingmapping",
            constraint=models.UniqueConstraint(fields=("tenant", "kind", "source_key"), name="uniq_accounting_mapping_source_per_tenant"),
        ),
        migrations.AddConstraint(
            model_name="accountingexportbatch",
            constraint=models.UniqueConstraint(fields=("tenant", "fingerprint"), name="uniq_accounting_export_fingerprint_per_tenant"),
        ),
    ]
