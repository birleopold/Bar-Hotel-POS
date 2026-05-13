from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(PlatformOperatorModelAdmin):
    list_display = ("created_at", "action", "entity_type", "entity_id", "tenant", "user")
    list_filter = ("action", "entity_type", "tenant")
    search_fields = ("entity_id",)
    readonly_fields = ("id", "tenant", "user", "action", "entity_type", "entity_id", "payload", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
