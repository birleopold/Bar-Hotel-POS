from __future__ import annotations

from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    MenuItemOutlet,
    MenuItemRecipeLine,
    ModifierGroup,
    ModifierOption,
    ServiceOffering,
    ServiceOfferingOption,
)

from .forms import (
    ConsoleMenuCategoryForm,
    ConsoleMenuItemForm,
    ConsoleMenuItemOutletCreateForm,
    ConsoleMenuItemOutletUpdateForm,
    ConsoleMenuItemRecipeLineForm,
    ConsoleModifierGroupForm,
    ConsoleModifierOptionForm,
    ConsoleServiceOfferingForm,
    ConsoleServiceOfferingOptionForm,
)
from .menu_sync import sync_menu_item_modifier_groups, sync_menu_item_outlet_links
from .mixins import ConsoleOrgAdminRequiredMixin


class MenuItemScopedMixin(ConsoleOrgAdminRequiredMixin):
    """Load ``menu_item`` for nested menu URLs."""

    menu_item: MenuItem

    def dispatch(self, request, *args, **kwargs):
        self.menu_item = get_object_or_404(
            MenuItem,
            pk=kwargs["item_id"],
            tenant_id=request.tenant.id,
        )
        return super().dispatch(request, *args, **kwargs)


class OrgMenuCategoryListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/menu_category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return MenuCategory.objects.filter(tenant=self.request.tenant).order_by("sort_order", "name")


class OrgMenuCategoryCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = MenuCategory
    form_class = ConsoleMenuCategoryForm
    template_name = "console/org/menu_category_form.html"
    success_url = reverse_lazy("console-org-menu-categories")

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        messages.success(self.request, f"Category “{form.instance.name}” created.")
        return super().form_valid(form)


class OrgMenuCategoryUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = MenuCategory
    form_class = ConsoleMenuCategoryForm
    template_name = "console/org/menu_category_form.html"
    pk_url_kwarg = "category_id"
    success_url = reverse_lazy("console-org-menu-categories")

    def get_queryset(self):
        return MenuCategory.objects.filter(tenant=self.request.tenant)

    def form_valid(self, form):
        messages.success(self.request, f"Category “{form.instance.name}” saved.")
        return super().form_valid(form)


class OrgMenuItemListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/menu_item_list.html"
    context_object_name = "items"

    def get_queryset(self):
        return (
            MenuItem.objects.filter(tenant=self.request.tenant)
            .select_related("category")
            .prefetch_related("outlets", "outlet_links", "recipe_lines")
            .order_by("category__sort_order", "category__name", "name")
        )


class OrgMenuItemCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = MenuItem
    form_class = ConsoleMenuItemForm
    template_name = "console/org/menu_item_form.html"
    success_url = reverse_lazy("console-org-menu-items")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        instance = form.save(commit=False)
        instance.tenant = self.request.tenant
        instance.save()
        sync_menu_item_outlet_links(instance, form.cleaned_data.get("outlets"))
        sync_menu_item_modifier_groups(instance, form.cleaned_data.get("modifier_groups"))
        self.object = instance
        messages.success(self.request, f"Item “{self.object.name}” created.")
        return redirect(self.get_success_url())


class OrgMenuItemUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = MenuItem
    form_class = ConsoleMenuItemForm
    template_name = "console/org/menu_item_form.html"
    pk_url_kwarg = "item_id"
    success_url = reverse_lazy("console-org-menu-items")

    def get_queryset(self):
        return MenuItem.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item_for_nav"] = self.object
        return ctx

    def form_valid(self, form):
        instance = form.save(commit=False)
        instance.save()
        sync_menu_item_outlet_links(instance, form.cleaned_data.get("outlets"))
        sync_menu_item_modifier_groups(instance, form.cleaned_data.get("modifier_groups"))
        self.object = instance
        messages.success(self.request, f"Item “{self.object.name}” saved.")
        return redirect(self.get_success_url())


class OrgMenuItemOutletListView(MenuItemScopedMixin, ListView):
    template_name = "console/org/menu_item_outlet_list.html"
    context_object_name = "links"

    def get_queryset(self):
        return (
            MenuItemOutlet.objects.filter(menu_item=self.menu_item)
            .select_related("outlet", "outlet__site")
            .order_by("outlet__site__name", "outlet__name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgMenuItemOutletCreateView(MenuItemScopedMixin, CreateView):
    model = MenuItemOutlet
    form_class = ConsoleMenuItemOutletCreateForm
    template_name = "console/org/menu_item_outlet_form.html"

    def _redirect_if_no_outlet_scope(self):
        if not self.menu_item.outlet_links.exists():
            messages.info(
                self.request,
                "On Edit item, choose one or more outlets under “Limit to outlets” first. "
                "Then you can add more outlet rows or price overrides here.",
            )
            return redirect("console-org-menu-item-edit", item_id=self.menu_item.pk)
        return None

    def get(self, request, *args, **kwargs):
        self.object = None
        r = self._redirect_if_no_outlet_scope()
        if r:
            return r
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        r = self._redirect_if_no_outlet_scope()
        if r:
            return r
        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["menu_item"] = self.menu_item
        kw["tenant"] = self.request.tenant
        return kw

    def get_success_url(self):
        return reverse("console-org-menu-item-outlets", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        outlet = form.cleaned_data["outlet"]
        if MenuItemOutlet.objects.filter(menu_item=self.menu_item, outlet=outlet).exists():
            messages.error(self.request, "That outlet is already linked; edit it instead.")
            return redirect(self.get_success_url())
        MenuItemOutlet.objects.create(
            menu_item=self.menu_item,
            outlet=outlet,
            price_override=form.cleaned_data.get("price_override"),
        )
        messages.success(self.request, f"Outlet “{outlet.name}” linked with pricing.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        ctx["form_title"] = "Add outlet pricing"
        return ctx


class OrgMenuItemOutletUpdateView(MenuItemScopedMixin, UpdateView):
    model = MenuItemOutlet
    form_class = ConsoleMenuItemOutletUpdateForm
    template_name = "console/org/menu_item_outlet_form.html"
    pk_url_kwarg = "link_id"

    def get_queryset(self):
        return MenuItemOutlet.objects.filter(menu_item=self.menu_item)

    def get_success_url(self):
        return reverse("console-org-menu-item-outlets", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        messages.success(self.request, "Outlet pricing updated.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        ctx["form_title"] = f"Pricing · {self.object.outlet.name}"
        return ctx


class OrgMenuItemOutletDeleteView(MenuItemScopedMixin, DeleteView):
    model = MenuItemOutlet
    template_name = "console/org/menu_item_outlet_confirm_delete.html"
    pk_url_kwarg = "link_id"

    def get_queryset(self):
        return MenuItemOutlet.objects.filter(menu_item=self.menu_item)

    def get_success_url(self):
        return reverse("console-org-menu-item-outlets", kwargs={"item_id": self.menu_item.pk})

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        name = obj.outlet.name
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Removed outlet link for “{name}”.")
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgMenuItemRecipeListView(MenuItemScopedMixin, ListView):
    template_name = "console/org/menu_item_recipe_list.html"
    context_object_name = "lines"

    def get_queryset(self):
        return (
            MenuItemRecipeLine.objects.filter(parent_item=self.menu_item)
            .select_related("ingredient_item")
            .order_by("ingredient_item__name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgMenuItemRecipeCreateView(MenuItemScopedMixin, CreateView):
    model = MenuItemRecipeLine
    form_class = ConsoleMenuItemRecipeLineForm
    template_name = "console/org/menu_item_recipe_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["parent_item"] = self.menu_item
        kw["tenant"] = self.request.tenant
        return kw

    def get_success_url(self):
        return reverse("console-org-menu-item-recipe", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        line = form.save(commit=False)
        line.parent_item = self.menu_item
        try:
            line.save()
        except IntegrityError:
            form.add_error(
                "ingredient_item",
                "That ingredient is already on this recipe.",
            )
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Ingredient “{line.ingredient_item.name}” added to recipe.",
        )
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        ctx["form_title"] = "Add recipe line"
        return ctx


class OrgMenuItemRecipeUpdateView(MenuItemScopedMixin, UpdateView):
    model = MenuItemRecipeLine
    form_class = ConsoleMenuItemRecipeLineForm
    template_name = "console/org/menu_item_recipe_form.html"
    pk_url_kwarg = "line_id"

    def get_queryset(self):
        return MenuItemRecipeLine.objects.filter(parent_item=self.menu_item)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["parent_item"] = self.menu_item
        kw["tenant"] = self.request.tenant
        return kw

    def get_success_url(self):
        return reverse("console-org-menu-item-recipe", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        messages.success(self.request, "Recipe line updated.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        ctx["form_title"] = f"Edit · {self.object.ingredient_item.name}"
        return ctx


class OrgMenuItemRecipeDeleteView(MenuItemScopedMixin, DeleteView):
    model = MenuItemRecipeLine
    template_name = "console/org/menu_item_recipe_confirm_delete.html"
    pk_url_kwarg = "line_id"

    def get_queryset(self):
        return MenuItemRecipeLine.objects.filter(parent_item=self.menu_item)

    def get_success_url(self):
        return reverse("console-org-menu-item-recipe", kwargs={"item_id": self.menu_item.pk})

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        ing = obj.ingredient_item.name
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Removed “{ing}” from recipe.")
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgServiceOfferingListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/service_offering_list.html"
    context_object_name = "services"

    def get_queryset(self):
        return (
            ServiceOffering.objects.filter(tenant=self.request.tenant)
            .prefetch_related("outlets", "options")
            .order_by("name")
        )


class OrgServiceOfferingCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = ServiceOffering
    form_class = ConsoleServiceOfferingForm
    template_name = "console/org/service_offering_form.html"
    success_url = reverse_lazy("console-org-service-offerings")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        instance = form.save(commit=False)
        instance.tenant = self.request.tenant
        instance.save()
        form.save_m2m()
        self.object = instance
        messages.success(self.request, f"Service “{self.object.name}” created.")
        return redirect(self.get_success_url())


class OrgServiceOfferingUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = ServiceOffering
    form_class = ConsoleServiceOfferingForm
    template_name = "console/org/service_offering_form.html"
    pk_url_kwarg = "service_id"
    success_url = reverse_lazy("console-org-service-offerings")

    def get_queryset(self):
        return ServiceOffering.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        messages.success(self.request, f"Service “{form.instance.name}” saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["service"] = self.object
        return ctx


class ServiceOfferingScopedMixin(ConsoleOrgAdminRequiredMixin):
    service: ServiceOffering

    def dispatch(self, request, *args, **kwargs):
        self.service = get_object_or_404(
            ServiceOffering,
            pk=kwargs["service_id"],
            tenant_id=request.tenant.id,
        )
        return super().dispatch(request, *args, **kwargs)


class OrgServiceOfferingOptionListView(ServiceOfferingScopedMixin, ListView):
    template_name = "console/org/service_offering_option_list.html"
    context_object_name = "options"

    def get_queryset(self):
        return ServiceOfferingOption.objects.filter(service_offering=self.service).order_by("sort_order", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["service"] = self.service
        return ctx


class OrgServiceOfferingOptionCreateView(ServiceOfferingScopedMixin, CreateView):
    model = ServiceOfferingOption
    form_class = ConsoleServiceOfferingOptionForm
    template_name = "console/org/service_offering_option_form.html"

    def get_success_url(self):
        return reverse("console-org-service-offering-options", kwargs={"service_id": self.service.id})

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.service_offering = self.service
        obj.save()
        messages.success(self.request, f"Package “{obj.name}” created.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["service"] = self.service
        ctx["form_title"] = "New service package"
        return ctx


class OrgServiceOfferingOptionUpdateView(ServiceOfferingScopedMixin, UpdateView):
    model = ServiceOfferingOption
    form_class = ConsoleServiceOfferingOptionForm
    template_name = "console/org/service_offering_option_form.html"
    pk_url_kwarg = "option_id"

    def get_queryset(self):
        return ServiceOfferingOption.objects.filter(service_offering=self.service)

    def get_success_url(self):
        return reverse("console-org-service-offering-options", kwargs={"service_id": self.service.id})

    def form_valid(self, form):
        messages.success(self.request, f"Package “{form.instance.name}” saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["service"] = self.service
        ctx["form_title"] = f"Edit package · {self.object.name}"
        return ctx


class OrgModifierGroupListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/modifier_group_list.html"
    context_object_name = "groups"

    def get_queryset(self):
        return ModifierGroup.objects.filter(tenant=self.request.tenant).order_by("name")


class OrgModifierGroupCreateView(ConsoleOrgAdminRequiredMixin, CreateView):
    model = ModifierGroup
    form_class = ConsoleModifierGroupForm
    template_name = "console/org/modifier_group_form.html"
    success_url = reverse_lazy("console-org-modifier-groups")

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        messages.success(self.request, f"Modifier group “{form.instance.name}” created.")
        return super().form_valid(form)


class OrgModifierGroupUpdateView(ConsoleOrgAdminRequiredMixin, UpdateView):
    model = ModifierGroup
    form_class = ConsoleModifierGroupForm
    template_name = "console/org/modifier_group_form.html"
    pk_url_kwarg = "group_id"
    success_url = reverse_lazy("console-org-modifier-groups")

    def get_queryset(self):
        return ModifierGroup.objects.filter(tenant=self.request.tenant)

    def form_valid(self, form):
        messages.success(self.request, f"Group “{form.instance.name}” saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modifier_group"] = self.object
        return ctx


class ModifierGroupScopedMixin(ConsoleOrgAdminRequiredMixin):
    modifier_group: ModifierGroup

    def dispatch(self, request, *args, **kwargs):
        self.modifier_group = get_object_or_404(
            ModifierGroup,
            pk=kwargs["group_id"],
            tenant_id=request.tenant.id,
        )
        return super().dispatch(request, *args, **kwargs)


class OrgModifierOptionListView(ModifierGroupScopedMixin, ListView):
    template_name = "console/org/modifier_option_list.html"
    context_object_name = "options"

    def get_queryset(self):
        return ModifierOption.objects.filter(group=self.modifier_group).order_by("sort_order", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modifier_group"] = self.modifier_group
        return ctx


class OrgModifierOptionCreateView(ModifierGroupScopedMixin, CreateView):
    model = ModifierOption
    form_class = ConsoleModifierOptionForm
    template_name = "console/org/modifier_option_form.html"

    def get_success_url(self):
        return reverse("console-org-modifier-options", kwargs={"group_id": self.modifier_group.id})

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.group = self.modifier_group
        obj.save()
        messages.success(self.request, f"Option “{obj.name}” created.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modifier_group"] = self.modifier_group
        ctx["form_title"] = "New option"
        return ctx


class OrgModifierOptionUpdateView(ModifierGroupScopedMixin, UpdateView):
    model = ModifierOption
    form_class = ConsoleModifierOptionForm
    template_name = "console/org/modifier_option_form.html"
    pk_url_kwarg = "option_id"

    def get_queryset(self):
        return ModifierOption.objects.filter(group=self.modifier_group)

    def get_success_url(self):
        return reverse("console-org-modifier-options", kwargs={"group_id": self.modifier_group.id})

    def form_valid(self, form):
        messages.success(self.request, f"Option “{form.instance.name}” saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modifier_group"] = self.modifier_group
        ctx["form_title"] = f"Edit · {self.object.name}"
        return ctx
