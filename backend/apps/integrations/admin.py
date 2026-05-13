from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import EfrisSubmission, IntegrationLink


@admin.register(IntegrationLink)
class IntegrationLinkAdmin(PlatformOperatorModelAdmin):
    list_display = ("provider_key", "label", "tenant", "is_enabled")
    list_filter = ("tenant", "is_enabled")


@admin.register(EfrisSubmission)
class EfrisSubmissionAdmin(PlatformOperatorModelAdmin):
    list_display = ("tenant", "status", "attempts", "provider_reference", "next_retry_at", "submitted_at")
    list_filter = ("status", "tenant")
    search_fields = ("provider_reference", "cashbook_entry__reference")
