import uuid
from django.db import migrations, models
from django.db.models.functions import Lower
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("catalog","0022_product_label_queue"),("purchasing","0017_package_snapshots")]
    operations=[
        migrations.CreateModel(
            name="SupplierProductCode",
            fields=[
                ("created_at",models.DateTimeField(auto_now_add=True)),
                ("updated_at",models.DateTimeField(auto_now=True)),
                ("id",models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),
                ("code",models.CharField(max_length=128)),
                ("description",models.CharField(blank=True,max_length=160)),
                ("is_active",models.BooleanField(default=True)),
                ("menu_item",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="supplier_codes",to="catalog.menuitem")),
                ("product_package",models.ForeignKey(blank=True,help_text="Optional package this supplier code identifies.",null=True,on_delete=django.db.models.deletion.CASCADE,related_name="supplier_codes",to="catalog.productpackage")),
                ("supplier",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="product_codes",to="purchasing.supplier")),
                ("tenant",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="supplier_product_codes",to="tenants.tenant")),
            ],
            options={"ordering":["supplier__name","menu_item__name","code"]},
        ),
        migrations.AddConstraint(
            model_name="supplierproductcode",
            constraint=models.UniqueConstraint(Lower("code"),"supplier",name="uniq_supplier_product_code_ci"),
        ),
    ]