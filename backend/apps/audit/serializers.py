from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
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
