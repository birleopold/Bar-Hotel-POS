from __future__ import annotations

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.lodging.models import RoomRateWindow

from .forms import ConsoleRoomRateWindowForm
from .mixins import ConsoleOrgAdminRequiredMixin


class OrgRoomRateWindowListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/room_rate_list.html"
    context_object_name = "windows"

    def get_queryset(self):
        return (
            RoomRateWindow.objects.filter(room_type__tenant=self.request.tenant)
            .select_related("room_type", "room_type__site")
            .order_by("room_type__site__name", "room_type__name", "valid_from")
        )


class OrgRoomRateWindowCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = RoomRateWindow
    form_class = ConsoleRoomRateWindowForm
    template_name = "console/org/room_rate_form.html"
    success_url = reverse_lazy("console-org-room-rates")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Rate window saved for {form.instance.room_type.name}.",
        )
        return super().form_valid(form)


class OrgRoomRateWindowUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = RoomRateWindow
    form_class = ConsoleRoomRateWindowForm
    template_name = "console/org/room_rate_form.html"
    pk_url_kwarg = "rate_id"
    success_url = reverse_lazy("console-org-room-rates")

    def get_queryset(self):
        return RoomRateWindow.objects.filter(room_type__tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        messages.success(self.request, "Rate window updated.")
        return super().form_valid(form)
