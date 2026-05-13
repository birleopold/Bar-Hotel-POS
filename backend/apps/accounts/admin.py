from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import Membership, User, UserInvite


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("tenant",)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_platform_staff")
    search_fields = ("email", "first_name", "last_name")
    inlines = [MembershipInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_platform_staff",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")


@admin.register(UserInvite)
class UserInviteAdmin(PlatformOperatorModelAdmin):
    list_display = ("email", "tenant", "role", "expires_at", "accepted_at", "created_at")
    list_filter = ("tenant", "role")
    search_fields = ("email",)
    autocomplete_fields = ("tenant", "invited_by")
    readonly_fields = ("token_hash", "accepted_at", "created_at", "updated_at")


@admin.register(Membership)
class MembershipAdmin(PlatformOperatorModelAdmin):
    list_display = ("user", "tenant", "role", "is_active")
    list_filter = ("tenant", "role", "is_active")
    autocomplete_fields = ("user", "tenant")
    filter_horizontal = ("sites", "outlets")
