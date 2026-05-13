from __future__ import annotations

from rest_framework import serializers

from apps.tenants.models import Site

from .models import CashbookEntry, FinanceCategory


class FinanceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FinanceCategory
        fields = [
            "id",
            "name",
            "kind",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "created_at", "updated_at")


class CashbookEntrySerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=FinanceCategory.objects.none())
    site = serializers.PrimaryKeyRelatedField(
        queryset=Site.objects.none(),
        allow_null=True,
        required=False,
    )
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_kind = serializers.CharField(source="category.kind", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True, allow_null=True)
    created_by_id = serializers.UUIDField(source="created_by.id", read_only=True, allow_null=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True, allow_null=True)

    class Meta:
        model = CashbookEntry
        fields = [
            "id",
            "category",
            "category_name",
            "category_kind",
            "site",
            "site_name",
            "amount",
            "transaction_date",
            "reference",
            "note",
            "created_by_id",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = (
            "id",
            "category_name",
            "category_kind",
            "site_name",
            "created_by_id",
            "created_by_email",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        if tenant is not None:
            self.fields["category"].queryset = FinanceCategory.objects.filter(tenant=tenant)
            self.fields["site"].queryset = Site.objects.filter(tenant=tenant)

    def validate_category(self, value: FinanceCategory) -> FinanceCategory:
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Category must belong to the current tenant.")
        return value

    def validate_site(self, value: Site | None) -> Site | None:
        if value is None:
            return value
        request = self.context["request"]
        if value.tenant_id != request.tenant.id:
            raise serializers.ValidationError("Site must belong to the current tenant.")
        membership = request.tenant_membership
        if membership.sites.exists() and value.id not in membership.sites.values_list("pk", flat=True):
            raise serializers.ValidationError("You cannot create or update entries for this site.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["tenant"] = request.tenant
        validated_data["created_by"] = request.user
        return super().create(validated_data)
