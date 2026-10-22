from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.common.admin_mixins import PlatformOperatorModelAdmin

from .models import Membership, User, UserInvite, PasswordRecoveryRequest


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


@admin.register(PasswordRecoveryRequest)
class PasswordRecoveryRequestAdmin(PlatformOperatorModelAdmin):
    list_display = ("user", "status", "requested_at", "approved_at", "expires_at", "approved_by")
    list_filter = ("status", "requested_at")
    search_fields = ("user__email",)
    readonly_fields = (
        "user", "status", "requested_at", "approved_at", "approved_by",
        "expires_at", "token_digest",
    )
    actions = ("approve_and_email", "deny_requests")

    @admin.action(description="Approve and email recovery link to account owner")
    def approve_and_email(self, request, queryset):
        from hashlib import sha256
        from datetime import timedelta
        from django.conf import settings
        from django.contrib import messages
        from django.contrib.auth.tokens import default_token_generator
        from django.db import transaction
        from django.utils import timezone
        from apps.api.password_views import _dispatch_password_reset_email, _uid_b64
        done = 0
        for item in queryset.filter(status="pending").select_related("user"):
            user = item.user
            if not user.is_active:
                continue
            if user.memberships.exists() and not user.memberships.filter(
                is_active=True, tenant__is_active=True
            ).exists():
                continue
            # A platform operator approves an account recovery, not re-employment.
            token = default_token_generator.make_token(user)
            with transaction.atomic():
                locked = PasswordRecoveryRequest.objects.select_for_update().get(pk=item.pk)
                if locked.status != "pending":
                    continue
                locked.status = "sent"
                locked.approved_by = request.user
                locked.approved_at = timezone.now()
                locked.expires_at = timezone.now() + timedelta(minutes=30)
                locked.token_digest = sha256(token.encode()).hexdigest()
                locked.save(update_fields=[
                    "status", "approved_by", "approved_at", "expires_at", "token_digest"
                ])
                from django.db import transaction as db_transaction
                # Dispatch only after the approved record commits.
                db_transaction.on_commit(
                    lambda u=user, t=token: _dispatch_password_reset_email(
                        user=u, uid=_uid_b64(u), token=t
                    )
                )
            done += 1
        self.message_user(request, f"Approved {done} eligible requests. Email dispatch is queued after commit.")

    @admin.action(description="Deny selected recovery requests")
    def deny_requests(self, request, queryset):
        total = queryset.filter(status="pending").update(status="denied")
        self.message_user(request, f"Denied {total} pending requests.")
