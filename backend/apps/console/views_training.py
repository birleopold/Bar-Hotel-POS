from __future__ import annotations

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.tenants.models import TrainingWorkspaceState
from apps.tenants.training import (
    EXERCISES,
    seed_retail_training_workspace,
    set_training_exercise_progress,
)

from .mixins import ConsoleOrgAdminRequiredMixin


class TrainingResetForm(forms.Form):
    confirmation = forms.CharField(
        label='Type RESET TRAINING',
        widget=forms.TextInput(attrs={'class': 'staff-input', 'autocomplete': 'off'}),
    )
    password = forms.CharField(
        label='Your account password',
        widget=forms.PasswordInput(
            attrs={'class': 'staff-input', 'autocomplete': 'current-password'}
        ),
    )

    def clean_confirmation(self):
        value = (self.cleaned_data.get('confirmation') or '').strip()
        if value != 'RESET TRAINING':
            raise forms.ValidationError('Type RESET TRAINING exactly.')
        return value


class OrgTrainingWorkspaceView(ConsoleOrgAdminRequiredMixin, View):
    template_name = 'console/org/training_workspace.html'

    def dispatch(self, request, *args, **kwargs):
        tenant = getattr(request, 'tenant', None)
        if tenant is None or not tenant.is_training:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def _state(self, request):
        return TrainingWorkspaceState.objects.filter(
            tenant=request.tenant
        ).select_related('seeded_by').first()

    def _exercise_rows(self, state):
        progress = state.exercise_progress if state else {}
        rows = []
        route_map = {
            'cashier_scan': ('staff-retail-pos-entry', 'Open checkout'),
            'cashier_hold': ('staff-pos-checkout', 'Open checkout'),
            'cashier_split': ('staff-pos-checkout', 'Open checkout'),
            'cashier_return': ('staff-sales', 'Open Sales Summary'),
            'stock_review': ('staff-inventory-balances', 'Open stock balances'),
            'po_receive': ('staff-purchasing-orders', 'Open purchase orders'),
            'stock_count': ('staff-inventory-counts', 'Open stock counts'),
            'manager_sales': ('staff-sales-summary', 'Open Sales Summary'),
            'manager_exception': ('staff-management', 'Open Management'),
            'manager_accounting': ('staff-accounting-export', 'Open accounting export'),
        }
        for role, items in EXERCISES.items():
            role_rows = []
            for item in items:
                record = progress.get(item['key']) or {}
                route_name, action_label = route_map.get(
                    item['key'], ('staff-dashboard', 'Open workspace')
                )
                try:
                    action_url = reverse(route_name)
                except Exception:
                    action_url = reverse('staff-dashboard')
                role_rows.append({
                    **item,
                    'completed': bool(record.get('completed')),
                    'updated_at': record.get('updated_at', ''),
                    'action_url': action_url,
                    'action_label': action_label,
                })
            rows.append({'role': role, 'items': role_rows})
        return rows

    def _context(self, request, *, reset_form=None):
        state = self._state(request)
        sample_ids = state.sample_ids if state else {}
        return {
            'training_state': state,
            'training_exercises': self._exercise_rows(state),
            'training_seeded': bool(state and state.sample_ids),
            'training_sample_counts': {
                'products': len(sample_ids.get('menu_item_ids', [])),
                'customers': len(sample_ids.get('customer_ids', [])),
                'suppliers': len(sample_ids.get('supplier_ids', [])),
                'purchase_orders': len(sample_ids.get('purchase_order_ids', [])),
                'sales': len(sample_ids.get('order_ids', [])),
                'returns': len(sample_ids.get('return_ids', [])),
            },
            'reset_form': reset_form or TrainingResetForm(),
        }

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        action = (request.POST.get('action') or '').strip()
        if action == 'seed':
            try:
                _state, replay = seed_retail_training_workspace(
                    tenant=request.tenant,
                    user=request.user,
                    reset=False,
                )
            except DRFValidationError as exc:
                messages.error(request, str(exc.detail))
            else:
                messages.success(
                    request,
                    'Training sample pack is already ready.'
                    if replay
                    else 'Retail training sample pack created.',
                )
            return redirect('console-org-training')

        if action == 'exercise':
            key = (request.POST.get('exercise_key') or '').strip()
            completed = request.POST.get('completed') == '1'
            try:
                set_training_exercise_progress(
                    tenant=request.tenant,
                    user=request.user,
                    exercise_key=key,
                    completed=completed,
                )
            except (TrainingWorkspaceState.DoesNotExist, DRFValidationError) as exc:
                messages.error(request, str(getattr(exc, 'detail', exc)))
            return redirect('console-org-training')

        if action == 'reset':
            form = TrainingResetForm(request.POST)
            if form.is_valid() and not request.user.check_password(
                form.cleaned_data['password']
            ):
                form.add_error(
                    'password',
                    'Confirm your account password to reset training data.',
                )
            if not form.is_valid():
                return render(
                    request,
                    self.template_name,
                    self._context(request, reset_form=form),
                    status=400,
                )
            try:
                state, _ = seed_retail_training_workspace(
                    tenant=request.tenant,
                    user=request.user,
                    reset=True,
                )
            except DRFValidationError as exc:
                messages.error(request, str(exc.detail))
            else:
                messages.success(
                    request,
                    f'Training sample pack reset to generation {state.generation}. '
                    'Users, roles, domains, sections and workstation configuration were preserved.',
                )
            return redirect('console-org-training')

        return render(
            request,
            self.template_name,
            self._context(request),
            status=400,
        )
