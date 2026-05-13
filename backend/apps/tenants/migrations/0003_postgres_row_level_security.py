# Optional PostgreSQL row-level security. No-op on SQLite.
# Requires ``POSTGRES_SET_REQUEST_TENANT_GUC=True`` and middleware that runs
# ``SET LOCAL app.tenant_id`` inside a per-request transaction (see settings).

from django.db import migrations


def _enable_rls(schema_editor) -> None:
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return
    cursor = conn.cursor()

    def policy_direct(table: str) -> None:
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        cursor.execute(
            f'''
            CREATE POLICY tenant_isolation ON "{table}"
            FOR ALL
            USING (tenant_id::text = current_setting('app.tenant_id', true));
            '''
        )

    def policy_sql(table: str, using: str) -> None:
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        cursor.execute(
            f'CREATE POLICY tenant_isolation ON "{table}" FOR ALL USING ({using});'
        )

    direct = (
        "accounts_membership",
        "audit_auditevent",
        "catalog_menucategory",
        "catalog_menuitem",
        "inventory_stockbalance",
        "inventory_stockmovement",
        "inventory_stockcountsession",
        "lodging_roomtype",
        "lodging_reservation",
        "lodging_folio",
        "lodging_folioline",
        "pos_order",
        "pos_payment",
        "pos_refund",
        "purchasing_supplier",
        "purchasing_purchaseorder",
        "tenants_site",
        "tenants_tenantsettings",
    )
    for t in direct:
        policy_direct(t)

    policy_sql(
        "tenants_outlet",
        """EXISTS (
            SELECT 1 FROM tenants_site s
            WHERE s.id = tenants_outlet.site_id
            AND s.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "pos_orderline",
        """EXISTS (
            SELECT 1 FROM pos_order o
            WHERE o.id = pos_orderline.order_id
            AND o.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "pos_table",
        """EXISTS (
            SELECT 1 FROM tenants_outlet ou
            JOIN tenants_site s ON s.id = ou.site_id
            WHERE ou.id = pos_table.outlet_id
            AND s.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "catalog_menuitemoutlet",
        """EXISTS (
            SELECT 1 FROM catalog_menuitem m
            WHERE m.id = catalog_menuitemoutlet.menu_item_id
            AND m.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "purchasing_purchaseorderline",
        """EXISTS (
            SELECT 1 FROM purchasing_purchaseorder po
            WHERE po.id = purchasing_purchaseorderline.purchase_order_id
            AND po.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "inventory_stockcountline",
        """EXISTS (
            SELECT 1 FROM inventory_stockcountsession cs
            WHERE cs.id = inventory_stockcountline.session_id
            AND cs.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )
    policy_sql(
        "lodging_room",
        """EXISTS (
            SELECT 1 FROM lodging_roomtype rt
            WHERE rt.id = lodging_room.room_type_id
            AND rt.tenant_id::text = current_setting('app.tenant_id', true)
        )""",
    )


def _disable_rls(schema_editor) -> None:
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return
    cursor = conn.cursor()
    tables = (
        "lodging_room",
        "inventory_stockcountline",
        "purchasing_purchaseorderline",
        "catalog_menuitemoutlet",
        "pos_table",
        "pos_orderline",
        "tenants_outlet",
        "accounts_membership",
        "audit_auditevent",
        "catalog_menucategory",
        "catalog_menuitem",
        "inventory_stockbalance",
        "inventory_stockmovement",
        "inventory_stockcountsession",
        "lodging_roomtype",
        "lodging_reservation",
        "lodging_folio",
        "lodging_folioline",
        "pos_order",
        "pos_payment",
        "pos_refund",
        "purchasing_supplier",
        "purchasing_purchaseorder",
        "tenants_site",
        "tenants_tenantsettings",
    )
    for t in tables:
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{t}";')
        cursor.execute(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY;')


def forwards(apps, schema_editor):
    _enable_rls(schema_editor)


def backwards(apps, schema_editor):
    _disable_rls(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_alter_outlet_outlet_type"),
        ("accounts", "0001_initial"),
        ("audit", "0001_initial"),
        ("catalog", "0003_menuitem_barcode_menuitem_reorder_level_and_more"),
        ("inventory", "0003_stockmovement_purchase_order"),
        ("lodging", "0002_folio_folioline"),
        ("pos", "0003_order_discount_amount_order_folio_and_more"),
        ("purchasing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
