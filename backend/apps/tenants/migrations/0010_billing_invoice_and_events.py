from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0009_control_plane_subscription_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BillingInvoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invoice_number", models.CharField(max_length=64)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("issued", "Issued"),
                            ("past_due", "Past due"),
                            ("paid", "Paid"),
                            ("void", "Void"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("external_ref", models.CharField(blank=True, max_length=128)),
                ("note", models.TextField(blank=True)),
                (
                    "subscription",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoices",
                        to="tenants.tenantsubscription",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="billing_invoices",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("tenant", "invoice_number")},
            },
        ),
        migrations.CreateModel(
            name="BillingEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("note", "Note"),
                            ("invoice_created", "Invoice created"),
                            ("invoice_status_changed", "Invoice status changed"),
                            ("subscription_status_changed", "Subscription status changed"),
                        ],
                        default="note",
                        max_length=40,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("previous_subscription_status", models.CharField(blank=True, max_length=16)),
                ("new_subscription_status", models.CharField(blank=True, max_length=16)),
                ("previous_invoice_status", models.CharField(blank=True, max_length=16)),
                ("new_invoice_status", models.CharField(blank=True, max_length=16)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="billing_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="events",
                        to="tenants.billinginvoice",
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="billing_events",
                        to="tenants.tenantsubscription",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="billing_events",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={"ordering": ["-occurred_at", "-created_at"]},
        ),
    ]
