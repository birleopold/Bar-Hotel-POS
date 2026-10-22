from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction

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

    def save_formset(self, request, form, formset, change):
        """Save tenant memberships within their own RLS scope.

        The central platform host has no request tenant. Django's default
        inline formset save() otherwise writes accounts_membership with no
        app.tenant_id and PostgreSQL correctly rejects it.
        """
        if formset.model is not Membership:
            return super().save_formset(request, form, formset, change)
        if not (
            request.user.is_authenticated
            and (request.user.is_superuser or getattr(request.user, "is_platform_staff", False))
        ):
            raise PermissionDenied("Only platform operators may edit tenant memberships.")

        # Django has validated all inline forms before calling save_formset.
        # Keep each membership and its sites/outlets m2m writes in the *same*
        # transaction with a tenant-specific SET LOCAL scope.
        for inline_form in formset.forms:
            if not inline_form.cleaned_data:
                continue
            instance = inline_form.instance
            deleting = bool(inline_form.cleaned_data.get("DELETE"))
            if not deleting and not inline_form.has_changed():
                continue
            tenant = inline_form.cleaned_data.get("tenant") or getattr(instance, "tenant", None)
            if tenant is None:
                raise ValueError("Membership must have a tenant before saving.")
            if instance.pk and str(instance.tenant_id) != str(tenant.pk):
                raise PermissionDenied("Move memberships by deleting and re-creating them.")
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.pk)])
                if deleting:
                    if instance.pk:
                        instance.delete()
                else:
                    inline_form.save()



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
        from apps.api.password_reset_core import recovery_eligible
        from urllib.parse import urlsplit
        template = getattr(settings, "PASSWORD_RESET_URL_TEMPLATE", "") or ""
        url = urlsplit(template)
        if url.scheme != "https" or not url.hostname or not url.path.endswith("/password-reset/confirm/"):
            self.message_user(
                request,
                "Set PASSWORD_RESET_URL_TEMPLATE to an HTTPS URL ending in "
                "/password-reset/confirm/?uid={uid}&token={token} before approving requests.",
                level=messages.ERROR,
            )
            return
        done = 0
        for item in queryset.filter(status="pending").select_related("user"):
            user = item.user
            if not recovery_eligible(user):
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
