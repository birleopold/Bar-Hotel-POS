import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_passwordrecoveryrequest"),
        ("catalog", "0016_serialized_inventory_settings"),
        ("inventory", "0018_retail_assembly_run_rls"),
        ("pos", "0034_orderline_seat_number"),
        ("purchasing", "0017_package_snapshots"),
        ("tenants", "0027_retail_assembly_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="InventorySerialUnit",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("serial_number", models.CharField(max_length=128)),
                ("secondary_identifier", models.CharField(blank=True, help_text="Optional secondary identifier such as IMEI2 or manufacturer serial.", max_length=128)),
                ("status", models.CharField(choices=[("available", "Available"), ("reserved", "Reserved for basket"), ("sold", "Sold"), ("returned", "Returned to stock"), ("quarantined", "Quarantined"), ("retired", "Retired / written off")], default="available", max_length=16)),
                ("received_at", models.DateField()),
                ("sold_at", models.DateTimeField(blank=True, null=True)),
                ("warranty_expires_at", models.DateField(blank=True, null=True)),
                ("note", models.CharField(blank=True, max_length=512)),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="serialized_units", to="catalog.menuitem")),
                ("outlet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="serialized_units", to="tenants.outlet")),
                ("purchase_receipt_line", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="serialized_units", to="purchasing.purchasereceiptline")),
                ("reserved_order_line", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reserved_serial_units", to="pos.orderline")),
                ("sold_order_line", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sold_serial_units", to="pos.orderline")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="serialized_units", to="tenants.tenant")),
            ],
            options={"ordering": ["menu_item__name", "serial_number"]},
        ),
        migrations.AddConstraint(
            model_name="inventoryserialunit",
            constraint=models.UniqueConstraint(fields=("tenant", "serial_number"), name="uniq_tenant_serial_number"),
        ),
        migrations.AddIndex(
            model_name="inventoryserialunit",
            index=models.Index(fields=["tenant", "outlet", "status"], name="serial_outlet_status_idx"),
        ),
        migrations.AddIndex(
            model_name="inventoryserialunit",
            index=models.Index(fields=["tenant", "menu_item", "status"], name="serial_item_status_idx"),
        ),
        migrations.CreateModel(
            name="InventorySerialEvent",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(choices=[("received", "Received"), ("reserved", "Reserved"), ("released", "Released"), ("sold", "Sold"), ("returned", "Returned"), ("transferred", "Transferred"), ("quarantined", "Quarantined"), ("retired", "Retired")], max_length=16)),
                ("note", models.CharField(blank=True, max_length=512)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="serialized_unit_events_created", to="accounts.user")),
                ("order_line", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="serialized_unit_events", to="pos.orderline")),
                ("outlet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="serialized_unit_events", to="tenants.outlet")),
                ("serial_unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="inventory.inventoryserialunit")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="serialized_unit_events", to="tenants.tenant")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
