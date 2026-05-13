from __future__ import annotations

import re

from rest_framework import serializers

from apps.accounts.models import Membership, User
from apps.tenants.models import Outlet, Site, TenantSettings

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class TenantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSettings
        fields = [
            "business_lines",
            "default_currency",
            "default_timezone",
            "receipt_footer",
            "theme_primary",
            "theme_secondary",
            "theme_accent",
            "logo_url",
            "efris_enabled",
        ]

    def _validate_hex(self, value: str) -> str:
        if value and not _HEX_COLOR.match(value):
            raise serializers.ValidationError("Use #RRGGBB hex format.")
        return value

    def validate_theme_primary(self, value: str) -> str:
        return self._validate_hex(value)

    def validate_theme_secondary(self, value: str) -> str:
        return self._validate_hex(value)

    def validate_theme_accent(self, value: str) -> str:
        return self._validate_hex(value)


class OutletBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Outlet
        fields = ["id", "name", "outlet_type", "is_active"]


class SiteBriefSerializer(serializers.ModelSerializer):
    outlets = serializers.SerializerMethodField()

    class Meta:
        model = Site
        fields = ["id", "name", "city", "is_active", "outlets"]

    def get_outlets(self, site: Site) -> list[dict]:
        membership: Membership | None = self.context.get("membership")
        qs = site.outlets.filter(is_active=True)
        if membership and membership.outlets.exists():
            qs = qs.filter(pk__in=membership.outlets.values_list("pk", flat=True))
        return OutletBriefSerializer(qs, many=True).data


class MembershipSerializer(serializers.ModelSerializer):
    tenant_id = serializers.UUIDField(source="tenant.id", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    tenant_slug = serializers.SlugField(source="tenant.slug", read_only=True)
    settings = serializers.SerializerMethodField()
    sites = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id",
            "role",
            "is_active",
            "tenant_id",
            "tenant_name",
            "tenant_slug",
            "settings",
            "sites",
        ]

    def get_settings(self, obj: Membership) -> dict | None:
        try:
            ts = obj.tenant.settings
        except TenantSettings.DoesNotExist:
            return None
        return TenantSettingsSerializer(ts).data

    def get_sites(self, obj: Membership) -> list[dict]:
        qs = Site.objects.filter(tenant=obj.tenant, is_active=True)
        if obj.sites.exists():
            qs = qs.filter(pk__in=obj.sites.values_list("pk", flat=True))
        qs = qs.order_by("name")
        return SiteBriefSerializer(
            qs,
            many=True,
            context={**self.context, "membership": obj},
        ).data


class MeSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "memberships"]

    def get_memberships(self, user: User) -> list[dict]:
        qs = (
            Membership.objects.filter(user=user, is_active=True)
            .select_related("tenant")
            .order_by("tenant__name")
        )
        return MembershipSerializer(qs, many=True, context=self.context).data
