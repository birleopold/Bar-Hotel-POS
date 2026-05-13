from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import EventBooking, EventSpace


@admin.register(EventSpace)
class EventSpaceAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "site", "capacity", "tenant", "is_active")


@admin.register(EventBooking)
class EventBookingAdmin(PlatformOperatorModelAdmin):
    list_display = ("title", "space", "start_at", "end_at", "status", "tenant")
    list_filter = ("status", "tenant")
