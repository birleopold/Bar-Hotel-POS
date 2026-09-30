from django import forms
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditEvent, ExceptionPolicy
from apps.audit.services import log_audit
from .mixins import StaffTenantRequiredMixin
from .services.permissions import membership_can_manage_workspace_settings
from .services.management import EXCEPTION_KINDS, MANAGER_ROLES, exception_assignees, update_exception_case, visible_cases, exception_rows, management_orders, management_scope, management_team, review_exception
from .services.dashboard_insights import dashboard_operations_snapshot


class ExceptionPolicyForm(forms.ModelForm):
    class Meta:
        model = ExceptionPolicy
        fields = ["cash_variance_threshold", "refund_threshold", "lookback_days", "discount_threshold", "stock_adjustment_threshold", "pin_failure_threshold", "offline_age_hours"]

    def __init__(self, *args, **kwargs):
        if args and args[0] is not None:
            data = args[0].copy()
            instance = kwargs.get("instance") or ExceptionPolicy()
            for name in ("discount_threshold", "stock_adjustment_threshold", "pin_failure_threshold", "offline_age_hours"):
                data.setdefault(name, getattr(instance, name))
            args = (data, *args[1:])
        super().__init__(*args, **kwargs)
        self.fields["cash_variance_threshold"].help_text = "Flag absolute cash differences greater than this amount. Zero flags any difference."
        self.fields["refund_threshold"].help_text = "Flag refunds at or above this amount in their recorded currency; no exchange-rate conversion. Zero includes all refunds."
        self.fields["lookback_days"].help_text = "Financial and PIN events from the last 1–365 days; current stock and overdue stays have no age limit."
        self.fields["discount_threshold"].help_text = "Flag discounts above this amount in their recorded currency."
        self.fields["stock_adjustment_threshold"].help_text = "Flag absolute stock changes above this quantity in the item's recorded units."
        self.fields["pin_failure_threshold"].help_text = "Flag recorded consecutive PIN failures at or above 1–5 attempts."
        self.fields["offline_age_hours"].help_text = "Flag pending offline operations after 1–168 hours; failed operations are always flagged."
        for field in self.fields.values():
            field.widget.attrs["class"] = "staff-input"


class ExceptionReviewForm(forms.Form):
    kind = forms.ChoiceField(choices=[(k, k) for k in EXCEPTION_KINDS])
    entity_id = forms.UUIDField()
    fingerprint = forms.RegexField(regex=r"^[a-f0-9]{64}$")
    status = forms.ChoiceField(choices=[("reviewed", "Reviewed"), ("open", "Open"), ("follow_up", "Follow up"), ("resolved", "Resolved review")])
    note = forms.CharField(max_length=1000)
    assigned_to = forms.UUIDField(required=False)
    due_date = forms.DateField(required=False)


class ExceptionCaseForm(ExceptionReviewForm):
    kind = None
    entity_id = None
    fingerprint = None
    case_id = forms.IntegerField(min_value=1)


class StaffManagementView(StaffTenantRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        member = getattr(request, "tenant_membership", None)
        if member and member.role not in MANAGER_ROLES:
            return HttpResponseForbidden("This workspace is available to managers only.")
        return super().dispatch(request, *args, **kwargs)

    def _render(self, request, *, policy_form=None, error="", status=200):
        mode = request.GET.get("view", "exceptions")
        if mode not in {"today", "exceptions", "approvals", "team", "reports", "cases"}:
            raise Http404
        outlets, modules, vis = management_scope(request)
        ctx = {"management_view": mode, "management_title": {"today": "Today", "exceptions": "Exceptions", "approvals": "Approval actions", "team": "Team", "reports": "Reports", "cases": "Case history and follow-up"}[mode], "management_outlets": outlets, "management_error": error}
        if mode == "exceptions":
            rows, policy = exception_rows(request)
            ctx.update(exception_rows=rows, exception_policy=policy, exception_assignees=exception_assignees(request))
            can_configure = membership_can_manage_workspace_settings(request.tenant_membership) and not request.session.get("staff_pin_authenticated")
            ctx["can_configure_exceptions"] = can_configure
            ctx["policy_form"] = policy_form or ExceptionPolicyForm(instance=policy)
        elif mode == "cases":
            cases = visible_cases(request)
            state = request.GET.get("state")
            if state in {"open", "reviewed", "follow_up", "resolved"}:
                cases = cases.filter(status=state)
            cases = list(cases[:100])
            history = {}
            for event in AuditEvent.objects.filter(tenant=request.tenant, action="exception.reviewed", entity_id__in=[str(case.pk) for case in cases]).select_related("user").order_by("-created_at")[:200]:
                history.setdefault(event.entity_id, []).append(event)
            for case in cases:
                case.assessment_history = history.get(str(case.pk), [])
            ctx.update(exception_cases=cases, exception_assignees=exception_assignees(request))
        elif mode == "approvals":
            ctx["approval_orders"] = management_orders(request)
        elif mode == "team":
            ctx["team_members"] = management_team(request)
            if vis.workspace and membership_can_manage_workspace_settings(request.tenant_membership):
                ctx["team_manage_url"] = reverse("staff-workspace-members")
        elif mode == "today":
            ctx["management_metrics"] = dashboard_operations_snapshot(request, membership=request.tenant_membership, modules=modules, vis=vis)
        reports = []
        if vis.sales and outlets:
            reports.append(("Sales report", reverse("staff-sales")))
            today = timezone.localdate().isoformat()
            ctx["today_sales_url"] = reverse("staff-sales") + f"?date_from={today}&date_to={today}"
        for enabled, route, label in [(vis.finance, "staff-finance-entries", "Income and expenses"), (vis.inventory, "staff-inventory-balances", "Stock balances"), (vis.lodging, "staff-lodging-reservations", "Stays")]:
            if enabled:
                reports.append((label, reverse(route)))
        ctx["management_reports"] = reports
        return render(request, "staff/management.html", ctx, status=status)

    def _assignee(self, request, data):
        selected = data.get("assigned_to")
        if selected:
            user = exception_assignees(request).filter(pk=selected).first()
            if user is None:
                raise ValidationError("Choose an authorized manager in your scope.")
            data["assigned_to"] = user
        return data

    def get(self, request):
        return self._render(request)

    @transaction.atomic
    def post(self, request):
        if request.POST.get("action") == "case":
            form = ExceptionCaseForm(request.POST)
            if not form.is_valid():
                return self._render(request, error="Provide a valid assessment, status and follow-up details.", status=400)
            try:
                data = self._assignee(request, form.cleaned_data)
                update_exception_case(request, **data)
            except ValidationError as exc:
                return self._render(request, error=str(exc.detail), status=409)
            messages.success(request, "Case assessment saved.")
            return redirect(reverse("staff-management") + "?view=cases")
        if request.GET.get("view", "exceptions") != "exceptions":
            return self._render(request, error="Use the exception review form.", status=400)
        if request.POST.get("action") == "policy":
            if not membership_can_manage_workspace_settings(request.tenant_membership) or request.session.get("staff_pin_authenticated"):
                return HttpResponseForbidden("Sign in with an owner or administrator account password to change exception thresholds.")
            policy, _ = ExceptionPolicy.objects.get_or_create(tenant=request.tenant)
            policy = ExceptionPolicy.objects.select_for_update().get(pk=policy.pk)
            before = {f: str(getattr(policy, f)) for f in ExceptionPolicyForm.Meta.fields}
            form = ExceptionPolicyForm(request.POST, instance=policy)
            if not form.is_valid():
                return self._render(request, policy_form=form, status=400)
            form.save()
            log_audit(tenant_id=request.tenant.pk, user_id=request.user.pk, action="exception.policy_updated", entity_type="exception_policy", entity_id=str(policy.pk), payload={"before": before, "after": {f: str(getattr(policy, f)) for f in form.Meta.fields}})
            messages.success(request, "Exception thresholds updated.")
        else:
            form = ExceptionReviewForm(request.POST)
            if not form.is_valid():
                return self._render(request, error="Choose a valid exception and add an assessment of up to 1,000 characters.", status=400)
            try:
                data = self._assignee(request, form.cleaned_data)
                data["entity_id"] = str(data["entity_id"])
                review_exception(request, **data)
            except ValidationError as exc:
                return self._render(request, error=str(exc.detail), status=409)
            messages.success(request, "Assessment saved. Source balances and transaction approvals are unchanged.")
        return redirect("staff-management")


class StaffManagementShiftView(StaffManagementView):
    http_method_names = ["get", "head", "options"]

    def get(self, request, shift_id):
        from apps.pos.models import PosShift
        outlets, modules, vis = management_scope(request)
        if "pos" not in modules or not vis.orders:
            raise Http404
        shift = get_object_or_404(PosShift.objects.select_related("outlet", "workstation", "opened_by", "closed_by"), tenant=request.tenant, outlet__in=outlets, pk=shift_id)
        variance = shift.counted_cash - shift.expected_cash if shift.counted_cash is not None else None
        return render(request, "staff/management_shift.html", {"shift": shift, "variance": variance})


class StaffManagementSourceView(StaffManagementView):
    http_method_names = ["get", "head", "options"]

    def get(self, request, kind, entity_id):
        if kind not in EXCEPTION_KINDS:
            raise Http404
        rows, _ = exception_rows(request, source=(kind, str(entity_id)))
        if not rows:
            raise Http404
        return render(request, "staff/management_source.html", {"exception": rows[0]})
