from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import resolve_url
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.generic import FormView, ListView, UpdateView, View

from apps.accounts.invite_service import create_user_invite
from apps.accounts.models import Membership, MembershipRole, User, UserInvite
from apps.api.password_views import build_password_reset_email_body
from apps.audit.services import log_audit
from apps.tenants.models import Outlet

from .forms import StaffMembershipBulkActionForm, StaffMembershipManageForm, StaffTeamInviteForm, StaffWorkerCreateForm
from .mixins import StaffTenantRequiredMixin
from .services import membership_can_manage_workspace_settings


def _owner_admin_count(tenant, *, exclude_membership_id: uuid.UUID | None = None) -> int:
    qs = Membership.objects.filter(
        tenant=tenant,
        is_active=True,
        role__in=[MembershipRole.OWNER, MembershipRole.TENANT_ADMIN],
    )
    if exclude_membership_id is not None:
        qs = qs.exclude(pk=exclude_membership_id)
    return qs.count()


def _membership_edit_would_break_admin_cover(membership: Membership, *, new_role: str, is_active: bool) -> bool:
    if membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
        return False
    if is_active and new_role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
        return False
    return _owner_admin_count(membership.tenant, exclude_membership_id=membership.id) == 0


def _build_reset_link(request, user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(str(user.pk)))
    token = default_token_generator.make_token(user)
    path = f"{resolve_url('staff-password-reset-confirm')}?uid={uid}&token={token}"
    return request.build_absolute_uri(path)


def _audit_membership(request, *, action: str, membership: Membership, payload: dict | None = None) -> None:
    log_audit(
        tenant_id=request.tenant.id,
        user_id=request.user.id,
        action=action,
        entity_type="membership",
        entity_id=str(membership.id),
        payload=payload or {},
        source="staff",
    )


class StaffInviteListView(StaffTenantRequiredMixin, ListView):
    """Pending and past invites for the workspace (same rules as API invite create)."""

    staff_nav_capability = "workspace"
    template_name = "staff/settings/invites_list.html"
    context_object_name = "invites"
    paginate_by = 40

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can view workspace invites.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.new_invite_token = request.session.pop("staff_invite_flash_token", None)
        self.new_invite_meta = request.session.pop("staff_invite_flash_meta", None)
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return UserInvite.objects.filter(tenant=self.request.tenant).select_related("invited_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_manage_invites"] = membership_can_manage_workspace_settings(
            self.request.tenant_membership
        )
        ctx["new_invite_token"] = getattr(self, "new_invite_token", None)
        ctx["new_invite_meta"] = getattr(self, "new_invite_meta", None)
        ctx["now"] = timezone.now()
        return ctx


class StaffInviteCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "workspace"
    form_class = StaffTeamInviteForm
    template_name = "staff/settings/invite_form.html"
    success_url = reverse_lazy("staff-workspace-invites")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(
                request,
                "Only an owner or tenant admin can send workspace invites.",
            )
            return redirect("staff-workspace-invites")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        inv, raw = create_user_invite(
            tenant=self.request.tenant,
            email=form.cleaned_data["email"],
            role=form.cleaned_data["role"],
            expires_days=form.cleaned_data["expires_days"],
            invited_by=self.request.user,
        )
        # Invitations share the same branch/outlet restrictions as direct worker creation.
        inv.sites.set(form.cleaned_data.get("sites") or [])
        inv.outlets.set(form.cleaned_data.get("outlets") or [])
        self.request.session["staff_invite_flash_token"] = raw
        self.request.session["staff_invite_flash_meta"] = {
            "email": inv.email,
            "role": inv.get_role_display(),
        }
        log_audit(
            tenant_id=self.request.tenant.id,
            user_id=self.request.user.id,
            action="workspace.invite.created",
            entity_type="user_invite",
            entity_id=str(inv.id),
            payload={"email": inv.email, "role": inv.role},
            source="staff",
        )
        messages.success(
            self.request,
            "Invite created. Copy the sign-up token on the next screen — it is only shown once.",
        )
        return super().form_valid(form)


class StaffInviteRegenerateView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "workspace"

    def post(self, request, invite_id, *args, **kwargs) -> HttpResponse:
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can manage workspace invites.")
            return redirect("staff-workspace-invites")
        inv = get_object_or_404(UserInvite, pk=invite_id, tenant=request.tenant)
        new_inv, raw = create_user_invite(
            tenant=request.tenant,
            email=inv.email,
            role=inv.role,
            expires_days=7,
            invited_by=request.user,
        )
        new_inv.sites.set(inv.sites.all())
        new_inv.outlets.set(inv.outlets.all())
        request.session["staff_invite_flash_token"] = raw
        request.session["staff_invite_flash_meta"] = {
            "email": new_inv.email,
            "role": new_inv.get_role_display(),
        }
        log_audit(
            tenant_id=request.tenant.id,
            user_id=request.user.id,
            action="workspace.invite.regenerated",
            entity_type="user_invite",
            entity_id=str(new_inv.id),
            payload={"email": new_inv.email, "previous_invite_id": str(inv.id)},
            source="staff",
        )
        messages.success(request, "A fresh invite token is ready below.")
        return redirect("staff-workspace-invites")


class StaffMembershipListView(StaffTenantRequiredMixin, ListView):
    """Workspace members directory and management entrypoint."""

    staff_nav_capability = "workspace"
    template_name = "staff/settings/members_list.html"
    context_object_name = "memberships"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can view workspace members.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = (
            Membership.objects.filter(tenant=self.request.tenant)
            .select_related("user")
            .prefetch_related("sites", "outlets")
            .order_by("-is_active", "user__email")
        )
        actor = self.request.tenant_membership
        if actor.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
            allowed_sites = actor.sites.values_list("pk", flat=True)
            qs = qs.filter(sites__in=allowed_sites).distinct().exclude(role__in=[MembershipRole.OWNER, MembershipRole.TENANT_ADMIN])
            qs = qs.exclude(pk=actor.pk)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(user__email__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q))
        role = (self.request.GET.get("role") or "").strip()
        if role:
            qs = qs.filter(role=role)
        status_filter = (self.request.GET.get("status") or "").strip()
        if status_filter == "active":
            qs = qs.filter(is_active=True)
        elif status_filter == "inactive":
            qs = qs.filter(is_active=False)
        pin_filter = (self.request.GET.get("pin") or "").strip()
        if pin_filter == "ready":
            qs = qs.exclude(staff_pin_hash="")
        elif pin_filter == "missing":
            qs = qs.filter(staff_pin_hash="")
        site_id = (self.request.GET.get("site") or "").strip()
        if site_id:
            qs = qs.filter(sites__id=site_id)
        outlet_id = (self.request.GET.get("outlet") or "").strip()
        if outlet_id:
            qs = qs.filter(outlets__id=outlet_id)
        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_manage_members"] = membership_can_manage_workspace_settings(self.request.tenant_membership)
        ctx["filter_q"] = self.request.GET.get("q") or ""
        ctx["filter_role"] = self.request.GET.get("role") or ""
        ctx["filter_status"] = self.request.GET.get("status") or ""
        ctx["filter_pin"] = self.request.GET.get("pin") or ""
        ctx["filter_site"] = self.request.GET.get("site") or ""
        ctx["filter_outlet"] = self.request.GET.get("outlet") or ""
        ctx["role_choices"] = MembershipRole.choices
        ctx["now"] = timezone.now()
        actor = self.request.tenant_membership
        from apps.staff.services.membership import staff_accessible_outlets, sites_visible_for_membership

        allowed_sites = sites_visible_for_membership(actor)
        allowed_outlets = staff_accessible_outlets(actor)
        sites = self.request.tenant.sites.filter(pk__in=[s.pk for s in allowed_sites], is_active=True).order_by("name")
        outlets = Outlet.objects.filter(pk__in=[o.pk for o in allowed_outlets], is_active=True).select_related("site").order_by("site__name", "name")
        if actor.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
            sites = sites.filter(pk__in=actor.sites.values_list("pk", flat=True))
            outlet_ids = actor.outlets.values_list("pk", flat=True)
            outlets = outlets.filter(site__in=sites)
            if actor.outlets.exists():
                outlets = outlets.filter(pk__in=outlet_ids)
        ctx["sites"] = list(sites)
        ctx["outlets"] = list(
            outlets
        )
        ctx["bulk_form"] = StaffMembershipBulkActionForm(tenant=self.request.tenant)
        ctx["worker_reset_link"] = self.request.session.pop("staff_worker_reset_link", None)
        return ctx


class StaffWorkerCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "workspace"
    form_class = StaffWorkerCreateForm
    template_name = "staff/settings/worker_form.html"
    success_url = reverse_lazy("staff-workspace-members")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can create workers.")
            return redirect("staff-workspace-members")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "New worker"
        return ctx

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        created_user = False
        if user is None:
            user = User.objects.create_user(
                email=email,
                first_name=form.cleaned_data.get("first_name") or "",
                last_name=form.cleaned_data.get("last_name") or "",
                phone=form.cleaned_data.get("phone") or "",
            )
            created_user = True
        else:
            changed = False
            for field in ("first_name", "last_name", "phone"):
                new_value = form.cleaned_data.get(field) or getattr(user, field) or ""
                if new_value and getattr(user, field) != new_value:
                    setattr(user, field, new_value)
                    changed = True
            if changed:
                user.save(update_fields=["first_name", "last_name", "phone"])
        membership = Membership.objects.create(
            user=user,
            tenant=self.request.tenant,
            role=form.cleaned_data["role"],
            is_active=True,
        )
        membership.sites.set(form.cleaned_data.get("sites") or [])
        membership.outlets.set(form.cleaned_data.get("outlets") or [])
        reset_link = _build_reset_link(self.request, user)
        self.request.session["staff_worker_reset_link"] = {
            "email": user.email,
            "url": reset_link,
            "reset_message": build_password_reset_email_body(
                user_email=user.email,
                uid=urlsafe_base64_encode(force_bytes(str(user.pk))),
                token=default_token_generator.make_token(user),
            ),
        }
        _audit_membership(
            self.request,
            action="workspace.member.created",
            membership=membership,
            payload={"email": user.email, "created_user": created_user, "role": membership.role},
        )
        messages.success(self.request, "Worker created. Copy the password setup link from the members page.")
        return super().form_valid(form)


class StaffMembershipBulkActionView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "workspace"
    form_class = StaffMembershipBulkActionForm
    success_url = reverse_lazy("staff-workspace-members")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can manage workspace members.")
            return redirect("staff-workspace-members")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        memberships = list(form.cleaned_data["member_ids"])
        if any(
            membership.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)
            for membership in memberships
        ):
            form.add_error("member_ids", "Bulk actions cannot target owners or tenant admins.")
            return self.form_invalid(form)
        action = form.cleaned_data["action"]
        preset = form.cleaned_data.get("role_preset") or ""
        if action == "apply_preset":
            from .forms.workspace_forms import ROLE_PRESET_DEFAULTS

            target_role = ROLE_PRESET_DEFAULTS.get(preset, {}).get("role")
            if target_role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
                form.add_error("role_preset", "Role presets cannot grant owner or tenant admin access.")
                return self.form_invalid(form)
        updated = 0
        skipped = 0
        for membership in memberships:
            if membership.user_id == self.request.user.id and action == "deactivate":
                skipped += 1
                continue
            if action == "activate":
                membership.is_active = True
                membership.save(update_fields=["is_active", "updated_at"])
                _audit_membership(
                    self.request,
                    action="workspace.member.activated",
                    membership=membership,
                    payload={"email": membership.user.email},
                )
                updated += 1
            elif action == "deactivate":
                if _membership_edit_would_break_admin_cover(membership, new_role=membership.role, is_active=False):
                    skipped += 1
                    continue
                membership.is_active = False
                membership.save(update_fields=["is_active", "updated_at"])
                _audit_membership(
                    self.request,
                    action="workspace.member.deactivated",
                    membership=membership,
                    payload={"email": membership.user.email, "bulk": True},
                )
                updated += 1
        if action == "apply_preset":
            from .forms.workspace_forms import ROLE_PRESET_DEFAULTS

            role_value = ROLE_PRESET_DEFAULTS.get(preset, {}).get("role")
            if role_value:
                for membership in memberships:
                    if _membership_edit_would_break_admin_cover(membership, new_role=role_value, is_active=membership.is_active):
                        skipped += 1
                        continue
                    membership.role = role_value
                    membership.save(update_fields=["role", "updated_at"])
                    _audit_membership(
                        self.request,
                        action="workspace.member.updated",
                        membership=membership,
                        payload={"role": membership.role, "bulk": True, "preset": preset},
                    )
                    updated += 1
        if skipped:
            messages.warning(self.request, f"Bulk action applied to {updated} worker(s); skipped {skipped} protected selection(s).")
        else:
            messages.success(self.request, f"Bulk action applied to {updated} worker(s).")
        return super().form_valid(form)


class StaffMembershipUpdateView(StaffTenantRequiredMixin, UpdateView):
    staff_nav_capability = "workspace"
    model = Membership
    form_class = StaffMembershipManageForm
    template_name = "staff/settings/member_form.html"
    pk_url_kwarg = "membership_id"
    success_url = reverse_lazy("staff-workspace-members")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can manage workspace members.")
            return redirect("staff-workspace-members")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Membership.objects.filter(tenant=self.request.tenant).select_related("user")
        actor = self.request.tenant_membership
        if actor.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
            return qs
        return qs.filter(sites__in=actor.sites.values_list("pk", flat=True)).exclude(
            role__in=[MembershipRole.OWNER, MembershipRole.TENANT_ADMIN]
        ).exclude(pk=actor.pk).distinct()

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = f"Manage {self.object.user.email}"
        return ctx

    def form_valid(self, form):
        if self.object.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
            if form.cleaned_data.get("sites") or form.cleaned_data.get("outlets"):
                form.add_error("sites", "Tenant administrators cannot be restricted using worker branch assignments.")
                return self.form_invalid(form)
            if not _membership_edit_would_break_admin_cover(
                self.object,
                new_role=form.cleaned_data["role"],
                is_active=form.cleaned_data.get("is_active", True),
            ) and form.cleaned_data["role"] not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
                form.add_error("role", "Keep at least one active owner or tenant admin in this workspace.")
                return self.form_invalid(form)
        if self.object.user_id == self.request.user.id and not form.cleaned_data.get("is_active", True):
            form.add_error("is_active", "You cannot deactivate your own workspace access.")
            return self.form_invalid(form)
        if _membership_edit_would_break_admin_cover(
            self.object,
            new_role=form.cleaned_data["role"],
            is_active=form.cleaned_data.get("is_active", True),
        ):
            form.add_error("role", "Keep at least one active owner or tenant admin in this workspace.")
            return self.form_invalid(form)
        if form.cleaned_data["role"] not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
            if not form.cleaned_data.get("sites"):
                form.add_error("sites", "Assign at least one branch to this worker.")
                return self.form_invalid(form)
            if not form.cleaned_data.get("outlets") and not self.object.outlets.exists():
                from apps.staff.services.membership import ROLE_OUTLET_TYPES

                allowed_types = ROLE_OUTLET_TYPES.get(form.cleaned_data["role"])
                configured_types = set()
                try:
                    from apps.tenants.business_lines import normalize_business_lines, outlet_types_for_business_lines

                    configured_types = set(outlet_types_for_business_lines(normalize_business_lines(self.request.tenant.settings.business_lines)))
                except Exception:
                    pass
                allowed_types = configured_types if allowed_types is None else configured_types & set(allowed_types)
                if not any(
                    site.outlets.filter(is_active=True, outlet_type__in=allowed_types).exists()
                    for site in form.cleaned_data["sites"]
                ):
                    form.add_error("sites", "The selected branches have no active outlet compatible with this role.")
                    return self.form_invalid(form)
        response = super().form_valid(form)
        _audit_membership(
            self.request,
            action="workspace.member.updated",
            membership=self.object,
            payload={"role": self.object.role, "is_active": self.object.is_active},
        )
        messages.success(self.request, "Worker access updated.")
        return response


class StaffMembershipDeactivateView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "workspace"

    def post(self, request, membership_id, *args, **kwargs) -> HttpResponse:
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can manage workspace members.")
            return redirect("staff-workspace-members")
        actor = request.tenant_membership
        membership_qs = Membership.objects.filter(tenant=request.tenant)
        if actor.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN):
            membership_qs = membership_qs.filter(sites__in=actor.sites.values_list("pk", flat=True)).exclude(
                role__in=[MembershipRole.OWNER, MembershipRole.TENANT_ADMIN]
            ).exclude(pk=actor.pk).distinct()
        membership = get_object_or_404(membership_qs, pk=membership_id)
        if membership.user_id == request.user.id:
            messages.error(request, "You cannot deactivate your own workspace access.")
            return redirect("staff-workspace-members")
        if _membership_edit_would_break_admin_cover(membership, new_role=membership.role, is_active=False):
            messages.error(request, "Keep at least one active owner or tenant admin in this workspace.")
            return redirect("staff-workspace-members")
        membership.is_active = False
        try:
            membership.save(update_fields=["is_active", "updated_at"])
        except ProtectedError:
            messages.error(request, "This worker could not be deactivated right now.")
        else:
            _audit_membership(
                request,
                action="workspace.member.deactivated",
                membership=membership,
                payload={"email": membership.user.email},
            )
            messages.success(request, "Worker deactivated.")
        return redirect("staff-workspace-members")


class StaffMembershipPinRevokeView(StaffTenantRequiredMixin, View):
    """Managers can revoke access to the shared terminal without knowing a worker's PIN."""

    staff_nav_capability = "workspace"
    http_method_names = ["post", "options"]

    @transaction.atomic
    def post(self, request, membership_id, *args, **kwargs) -> HttpResponse:
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Only an owner or tenant admin can revoke worker PINs.")
            return redirect("staff-workspace-members")
        membership = get_object_or_404(Membership.objects.select_for_update(), pk=membership_id, tenant=request.tenant)
        if membership.user_id == request.user.id:
            messages.error(request, "Change your own PIN from Set PIN using your account password.")
            return redirect("staff-workspace-members")
        if not membership.staff_pin_hash:
            messages.info(request, "This worker does not have a terminal PIN.")
            return redirect("staff-workspace-members")
        membership.staff_pin_hash = ""
        membership.staff_pin_failures = 0
        membership.staff_pin_locked_until = None
        membership.save(update_fields=["staff_pin_hash", "staff_pin_failures", "staff_pin_locked_until", "updated_at"])
        _audit_membership(request, action="workspace.member.pin_revoked", membership=membership)
        messages.success(request, "Terminal PIN revoked. The worker can set a new PIN with their account password.")
        return redirect("staff-workspace-members")
