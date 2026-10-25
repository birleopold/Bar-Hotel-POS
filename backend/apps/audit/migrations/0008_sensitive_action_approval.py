import uuid

import django.db.models.deletion
from django.db import migrations, models


def apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "audit_sensitiveactionapproval" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "audit_sensitiveactionapproval";')
        cursor.execute(
            """CREATE POLICY tenant_isolation ON "audit_sensitiveactionapproval"
            FOR ALL USING (tenant_id::text = current_setting('app.tenant_id', true));"""
        )


def undo_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS tenant_isolation ON "audit_sensitiveactionapproval";')
        cursor.execute('ALTER TABLE "audit_sensitiveactionapproval" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0007_staffnotification_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="SensitiveActionApproval",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(db_index=True, max_length=32)),
                ("entity_type", models.CharField(max_length=32)),
                ("entity_id", models.CharField(db_index=True, max_length=64)),
                ("request_key", models.CharField(max_length=64)),
                ("intent_hash", models.CharField(max_length=64)),
                ("intent_payload", models.JSONField(blank=True, default=dict)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("approver", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sensitive_actions_approved",
                    to="accounts.membership",
                )),
                ("requester", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sensitive_actions_requested",
                    to="accounts.membership",
                )),
                ("scope_outlet", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sensitive_action_approvals",
                    to="tenants.outlet",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sensitive_action_approvals",
                    to="tenants.tenant",
                )),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant", "action", "request_key"),
                        name="uniq_sensitive_action_request",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["tenant", "action", "entity_id"],
                        name="sensitive_action_lookup_idx",
                    ),
                    models.Index(
                        fields=["tenant", "expires_at", "used_at"],
                        name="sensitive_action_expiry_idx",
                    ),
                ],
            },
        ),
        migrations.RunPython(apply_rls, undo_rls),
    ]
