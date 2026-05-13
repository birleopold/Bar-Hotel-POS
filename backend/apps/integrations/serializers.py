from rest_framework import serializers

from .models import IntegrationLink


class IntegrationLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationLink
        fields = [
            "id",
            "tenant",
            "provider_key",
            "label",
            "settings",
            "is_enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "tenant", "created_at", "updated_at")
