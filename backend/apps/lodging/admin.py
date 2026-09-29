from django.contrib import admin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import Folio, FolioLine, FolioPayment, Reservation, Room, RoomMaintenanceRequest, RoomRateWindow, RoomType


class FolioLineInline(admin.TabularInline):
    model = FolioLine
    extra = 0
    readonly_fields = ("source_order",)


class FolioPaymentInline(admin.TabularInline):
    model = FolioPayment
    extra = 0
    readonly_fields = ("amount", "method", "reference", "idempotency_key", "recorded_by", "created_at")


@admin.register(Folio)
class FolioAdmin(PlatformOperatorModelAdmin):
    list_display = ("guest_name", "site", "status", "currency", "tenant", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("guest_name", "notes")
    inlines = [FolioLineInline, FolioPaymentInline]
    autocomplete_fields = ("site", "reservation")


@admin.register(RoomRateWindow)
class RoomRateWindowAdmin(PlatformOperatorModelAdmin):
    list_display = ("room_type", "label", "valid_from", "valid_to", "nightly_amount")
    list_filter = ("room_type__tenant",)
    search_fields = ("label", "room_type__name")
    autocomplete_fields = ("room_type",)


@admin.register(RoomType)
class RoomTypeAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "site", "tenant", "max_occupancy", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)


@admin.register(Room)
class RoomAdmin(PlatformOperatorModelAdmin):
    list_display = ("name", "room_type", "status", "is_active")
    list_filter = ("status", "is_active")
    search_fields = ("name",)
    autocomplete_fields = ("room_type",)


@admin.register(Reservation)
class ReservationAdmin(PlatformOperatorModelAdmin):
    list_display = ("guest_name", "site", "check_in", "check_out", "status", "room")
    list_filter = ("status", "tenant")
    search_fields = ("guest_name", "guest_email")
    autocomplete_fields = ("room", "site")


@admin.register(RoomMaintenanceRequest)
class RoomMaintenanceRequestAdmin(PlatformOperatorModelAdmin):
    list_display = ("title", "room", "priority", "status", "assigned_to", "expected_by", "tenant")
    list_filter = ("status", "priority", "tenant")
    search_fields = ("title", "description", "room__name")
    autocomplete_fields = ("room", "assigned_to")
