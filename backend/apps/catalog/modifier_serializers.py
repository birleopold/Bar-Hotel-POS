from rest_framework import serializers

from .models import ModifierGroup, ModifierOption


class ModifierOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModifierOption
        fields = [
            "id",
            "group",
            "name",
            "price_delta",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_group(self, group):
        t = self.context["request"].tenant
        if group.tenant_id != t.id:
            raise serializers.ValidationError("Group must belong to the current tenant.")
        return group


class ModifierGroupSerializer(serializers.ModelSerializer):
    options = ModifierOptionSerializer(many=True, read_only=True)

    class Meta:
        model = ModifierGroup
        fields = [
            "id",
            "tenant",
            "name",
            "min_selections",
            "max_selections",
            "options",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "tenant", "options", "created_at", "updated_at")
