from rest_framework import serializers

from apps.staff.services.audit_reader import safe_audit_payload

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    payload = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "action",
            "entity_type",
            "entity_id",
            "payload",
            "user",
            "created_at",
        ]
        read_only_fields = (
            "id",
            "action",
            "entity_type",
            "entity_id",
            "payload",
            "user",
            "created_at",
        )

    def get_payload(self, obj):
        return safe_audit_payload(obj.payload or {})
