from __future__ import annotations

import base64
import hashlib
import json
import re
from itertools import product
from io import BytesIO

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from apps.tenants.models import Outlet, Tenant
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from apps.audit.services import log_audit
from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    MenuItemOutlet,
    MenuItemRecipeLine,
    ProductFamily,
    ProductPackage,
    RetailAssemblyComponent,
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
    ConsoleProductFamilyForm,
    ConsoleProductPackageForm,
    ConsoleRetailAssemblyComponentForm,
    ConsoleVariantMatrixForm,
    ConsoleModifierGroupForm,
    ConsoleModifierOptionForm,
    ConsoleServiceOfferingForm,
    ConsoleServiceOfferingOptionForm,
)
from .menu_sync import sync_menu_item_modifier_groups, sync_menu_item_outlet_links
from .mixins import ConsoleOrgAdminRequiredMixin


class RetailMerchandiseRequiredMixin(ConsoleOrgAdminRequiredMixin):
    """Keep retail merchandise tools out of hospitality-only workspaces."""

    def dispatch(self, request, *args, **kwargs):
        if getattr(request, "tenant", None) is not None:
            from .services import console_business_line_flags
            if not console_business_line_flags(request.tenant)["console_has_retail"]:
                messages.error(request, "Retail merchandise tools are available only when Retail or Supermarket is enabled.")
                return redirect("console-org-menu-items")
        return super().dispatch(request, *args, **kwargs)


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


class OrgProductFamilyListView(RetailMerchandiseRequiredMixin, ListView):
    template_name = "console/org/product_family_list.html"
    context_object_name = "families"

    def get_queryset(self):
        return (
            ProductFamily.objects.filter(tenant=self.request.tenant)
            .select_related("category")
            .prefetch_related("variants")
            .order_by("category__sort_order", "category__name", "name")
        )


class OrgProductFamilyCreateView(RetailMerchandiseRequiredMixin, CreateView):
    model = ProductFamily
    form_class = ConsoleProductFamilyForm
    template_name = "console/org/product_family_form.html"
    success_url = reverse_lazy("console-org-product-families")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        messages.success(self.request, f"Product family “{form.instance.name}” created.")
        return super().form_valid(form)


class OrgProductFamilyUpdateView(RetailMerchandiseRequiredMixin, UpdateView):
    model = ProductFamily
    form_class = ConsoleProductFamilyForm
    template_name = "console/org/product_family_form.html"
    pk_url_kwarg = "family_id"
    success_url = reverse_lazy("console-org-product-families")

    def get_queryset(self):
        return ProductFamily.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        messages.success(self.request, f"Product family “{form.instance.name}” saved.")
        return super().form_valid(form)


class OrgProductVariantMatrixView(RetailMerchandiseRequiredMixin, View):
    template_name = "console/org/product_variant_matrix.html"

    def _family(self, request, family_id):
        return get_object_or_404(
            ProductFamily.objects.select_related("category"),
            pk=family_id,
            tenant=request.tenant,
        )

    @staticmethod
    def _initial_from_family(family):
        initial = {}
        for index, row in enumerate((family.variant_schema or [])[:3], start=1):
            initial[f"option_{index}_name"] = row.get("name", "")
            initial[f"option_{index}_values"] = ", ".join(row.get("values", []))
        initial.setdefault("option_1_name", "Colour")
        initial.setdefault("option_2_name", "")
        first = family.variants.order_by("created_at").first()
        initial["sku_prefix"] = (
            (first.sku.split("-", 1)[0] if first and first.sku else "")
            or re.sub(r"[^A-Z0-9]+", "-", family.name.upper()).strip("-")[:24]
            or "ITEM"
        )
        initial["unit_price"] = first.unit_price if first else 0
        initial["tax_rate_percent"] = first.tax_rate_percent if first else None
        initial["reorder_level"] = first.reorder_level if first else None
        initial["track_inventory"] = first.track_inventory if first else True
        initial["is_active"] = first.is_active if first else True
        return initial

    @staticmethod
    def _variant_payload(schema, values):
        pairs = [{"name": row["name"], "value": value} for row, value in zip(schema, values)]
        snapshot = {row["name"]: value for row, value in zip(schema, values)}
        raw = json.dumps(
            [{"name": p["name"].casefold(), "value": p["value"].casefold()} for p in pairs],
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return snapshot, hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _sku(prefix, values, key):
        pieces = [re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")[:14] or "VAR" for value in values]
        candidate = "-".join([prefix, *pieces])
        if len(candidate) <= 64:
            return candidate
        return f"{candidate[:55].rstrip('-')}-{key[:8]}"

    def _combinations(self, schema):
        return list(product(*(row["values"] for row in schema)))

    def _render(self, request, family, form, *, preview=None, created_count=0):
        from django.shortcuts import render
        return render(request, self.template_name, {
            "family": family,
            "form": form,
            "preview_rows": preview or [],
            "created_count": created_count,
            "variants": family.variants.order_by("name"),
        })

    def get(self, request, family_id):
        family = self._family(request, family_id)
        return self._render(
            request,
            family,
            ConsoleVariantMatrixForm(initial=self._initial_from_family(family)),
        )

    def post(self, request, family_id):
        family = self._family(request, family_id)
        form = ConsoleVariantMatrixForm(request.POST)
        if not form.is_valid():
            return self._render(request, family, form)

        schema = form.cleaned_data["variant_schema"]
        combinations = self._combinations(schema)
        preview = []
        for values in combinations:
            snapshot, key = self._variant_payload(schema, values)
            preview.append({
                "values": " / ".join(values),
                "sku": self._sku(form.cleaned_data["sku_prefix"], values, key),
                "exists": family.variants.filter(variant_key=key).exists(),
                "snapshot": snapshot,
            })
        if request.POST.get("action") != "generate":
            return self._render(request, family, form, preview=preview)

        with transaction.atomic():
            family = ProductFamily.objects.select_for_update().get(
                pk=family.pk, tenant=request.tenant,
            )
            planned = []
            seen_skus = set()
            for values in combinations:
                snapshot, key = self._variant_payload(schema, values)
                if MenuItem.objects.filter(product_family=family, variant_key=key).exists():
                    continue
                sku = self._sku(form.cleaned_data["sku_prefix"], values, key)
                sku_fold = sku.casefold()
                if sku_fold in seen_skus:
                    form.add_error(None, f"Generated SKU collision for {' / '.join(values)}. Adjust the values or prefix.")
                    return self._render(request, family, form, preview=preview)
                seen_skus.add(sku_fold)
                if MenuItem.objects.filter(tenant=request.tenant, sku__iexact=sku).exists():
                    form.add_error(None, f"SKU {sku} already belongs to another product.")
                    return self._render(request, family, form, preview=preview)
                if ProductPackage.objects.filter(tenant=request.tenant, sku_alias__iexact=sku).exists():
                    form.add_error(None, f"SKU {sku} is already used by a product package.")
                    return self._render(request, family, form, preview=preview)
                name = f"{family.name} · {' / '.join(values)}"[:255]
                if MenuItem.objects.filter(tenant=request.tenant, name__iexact=name).exists():
                    form.add_error(None, f"Product name {name} already exists.")
                    return self._render(request, family, form, preview=preview)
                planned.append((name, sku, snapshot, key))

            family.variant_schema = schema
            family.save(update_fields=["variant_schema", "updated_at"])
            for name, sku, snapshot, key in planned:
                MenuItem.objects.create(
                    tenant=request.tenant,
                    category=family.category,
                    product_family=family,
                    variant_key=key,
                    variant_values=snapshot,
                    name=name,
                    sku=sku,
                    barcode="",
                    unit_of_measure="each",
                    track_inventory=form.cleaned_data["track_inventory"],
                    reorder_level=form.cleaned_data.get("reorder_level"),
                    unit_price=form.cleaned_data["unit_price"],
                    tax_rate_percent=form.cleaned_data.get("tax_rate_percent"),
                    is_active=form.cleaned_data["is_active"],
                )
            log_audit(
                tenant_id=request.tenant.pk,
                user_id=request.user.pk,
                action="catalog.variant_matrix_generated",
                entity_type="product_family",
                entity_id=str(family.pk),
                payload={
                    "schema": schema,
                    "created_count": len(planned),
                    "sku_prefix": form.cleaned_data["sku_prefix"],
                },
            )
        messages.success(request, f"Created {len(planned)} new variant SKU(s). Existing combinations were left unchanged.")
        return redirect("console-org-product-family-matrix", family_id=family.pk)


class OrgProductPackageListView(RetailMerchandiseRequiredMixin, MenuItemScopedMixin, ListView):
    template_name = "console/org/product_package_list.html"
    context_object_name = "packages"

    def get_queryset(self):
        return ProductPackage.objects.filter(
            tenant=self.request.tenant, menu_item=self.menu_item,
        ).order_by("units_per_package", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgProductPackageCreateView(RetailMerchandiseRequiredMixin, MenuItemScopedMixin, CreateView):
    model = ProductPackage
    form_class = ConsoleProductPackageForm
    template_name = "console/org/product_package_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["menu_item"] = self.menu_item
        return kw

    def get_success_url(self):
        return reverse("console-org-menu-item-packages", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        form.instance.menu_item = self.menu_item
        messages.success(self.request, f"Package “{form.instance.name}” added.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgProductPackageUpdateView(RetailMerchandiseRequiredMixin, MenuItemScopedMixin, UpdateView):
    model = ProductPackage
    form_class = ConsoleProductPackageForm
    template_name = "console/org/product_package_form.html"
    pk_url_kwarg = "package_id"

    def get_queryset(self):
        return ProductPackage.objects.filter(
            tenant=self.request.tenant, menu_item=self.menu_item,
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["menu_item"] = self.menu_item
        return kw

    def get_success_url(self):
        return reverse("console-org-menu-item-packages", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        messages.success(self.request, f"Package “{form.instance.name}” saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgMenuItemListView(ConsoleOrgAdminRequiredMixin, ListView):
    template_name = "console/org/menu_item_list.html"
    context_object_name = "items"

    def get_queryset(self):
        qs = (
            MenuItem.objects.filter(tenant=self.request.tenant)
            .select_related("category")
            .prefetch_related("outlets", "outlet_links", "recipe_lines")
            .order_by("category__sort_order", "category__name", "name")
        )
        if (self.request.GET.get("photo") or "").strip() == "missing":
            qs = qs.filter(product_image="", display_image_url="")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = MenuItem.objects.filter(tenant=self.request.tenant)
        ctx["missing_photo_count"] = base.filter(product_image="", display_image_url="").count()
        ctx["photo_filter"] = (self.request.GET.get("photo") or "").strip()
        return ctx


def _save_catalog_item_safely(view, form, *, creating):
    """Serialize console and cashier product registrations per tenant."""
    with transaction.atomic():
        Tenant.objects.select_for_update().get(pk=view.request.tenant.pk)
        name = form.cleaned_data["name"].strip()
        barcode = (form.cleaned_data.get("barcode") or "").strip()
        candidates = MenuItem.objects.filter(tenant=view.request.tenant)
        current = None
        before_price = None
        if not creating:
            current = MenuItem.objects.select_for_update().get(
                pk=view.object.pk, tenant=view.request.tenant
            )
            before_price = current.unit_price
            candidates = candidates.exclude(pk=view.object.pk)
        if candidates.filter(name__iexact=name).exists():
            form.add_error("name", "A product with this name already exists. Edit the existing product.")
            return view.form_invalid(form)
        if barcode and candidates.filter(barcode=barcode).exists():
            form.add_error("barcode", "This barcode is already registered to another product.")
            return view.form_invalid(form)
        if barcode and ProductPackage.objects.filter(
            tenant=view.request.tenant,
        ).filter(Q(barcode__iexact=barcode) | Q(sku_alias__iexact=barcode)).exists():
            form.add_error("barcode", "This code is already registered to a product package.")
            return view.form_invalid(form)
        sku = (form.cleaned_data.get("sku") or "").strip()
        if sku and ProductPackage.objects.filter(
            tenant=view.request.tenant,
        ).filter(Q(sku_alias__iexact=sku) | Q(barcode__iexact=sku)).exists():
            form.add_error("sku", "This code is already registered to a product package.")
            return view.form_invalid(form)
        instance = form.save(commit=False)
        if creating:
            instance.tenant = view.request.tenant
        elif "product_image" not in form.changed_data:
            # A phone may have uploaded a newer photo while this desktop form
            # was being filled. Keep the latest committed photo unless the
            # desktop user explicitly replaced or cleared it.
            instance.product_image = current.product_image
        instance.save()
        sync_menu_item_outlet_links(instance, form.cleaned_data.get("outlets"))
        sync_menu_item_modifier_groups(instance, form.cleaned_data.get("modifier_groups"))
        if not creating and before_price != instance.unit_price:
            explicit_outlet_ids = list(
                MenuItemOutlet.objects.filter(menu_item=instance)
                .values_list("outlet_id", flat=True)
            )
            affected_outlets = list(
                Outlet.objects.filter(
                    site__tenant=view.request.tenant,
                    pk__in=explicit_outlet_ids,
                ).only("id", "name")
                if explicit_outlet_ids
                else Outlet.objects.filter(
                    site__tenant=view.request.tenant,
                ).only("id", "name")
            )
            for outlet in affected_outlets:
                log_audit(
                    tenant_id=view.request.tenant.pk,
                    user_id=view.request.user.pk,
                    action="catalog.unit_price_changed",
                    entity_type="menu_item",
                    entity_id=str(instance.pk),
                    payload={
                        "item_name": instance.name,
                        "outlet_id": str(outlet.pk),
                        "outlet_name": outlet.name,
                        "before": str(before_price),
                        "after": str(instance.unit_price),
                        "applies_to_all_outlets": not bool(explicit_outlet_ids),
                    },
                )
        view.object = instance
    messages.success(view.request, f"Item “{view.object.name}” {'created' if creating else 'saved'}.")
    return redirect(view.get_success_url())


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
        return _save_catalog_item_safely(self, form, creating=True)


def _phone_photo_handoff_context(request, item: MenuItem) -> dict:
    """Build a same-account phone handoff without exposing a third-party QR service."""
    photo_path = reverse("console-org-menu-item-photo", kwargs={"item_id": item.pk})
    photo_url = request.build_absolute_uri(photo_path)
    qr_data_uri = ""
    try:
        import qrcode

        qr = qrcode.QRCode(version=None, box_size=6, border=2)
        qr.add_data(photo_url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        output = BytesIO()
        image.save(output, format="PNG")
        qr_data_uri = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except Exception:
        # Link/copy remains available if QR rendering is unavailable.
        qr_data_uri = ""
    return {
        "phone_photo_url": photo_url,
        "phone_photo_qr_data_uri": qr_data_uri,
        "can_notify_phone_account": bool(getattr(request, "tenant_membership", None)),
    }


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
        ctx.update(_phone_photo_handoff_context(self.request, self.object))
        return ctx

    def form_valid(self, form):
        return _save_catalog_item_safely(self, form, creating=False)


class OrgMenuItemPhotoView(ConsoleOrgAdminRequiredMixin, View):
    """Phone-friendly photo-only editor; does not overwrite desktop form fields."""

    template_name = "console/org/menu_item_photo.html"

    def get_product(self, request, item_id):
        return get_object_or_404(MenuItem, pk=item_id, tenant=request.tenant)

    def get(self, request, item_id):
        from django.http import JsonResponse
        from django.shortcuts import render

        item = self.get_product(request, item_id)
        if request.GET.get("status") == "1":
            response = JsonResponse({
                "image_url": item.product_image_render_src or "",
                "image_key": item.product_image.name if item.product_image else "",
            })
            response["Cache-Control"] = "private, no-store"
            return response
        return render(request, self.template_name, {"item": item})

    def post(self, request, item_id):
        from django import forms
        from django.shortcuts import render

        item = self.get_product(request, item_id)

        if request.POST.get("action") == "notify_phone":
            from apps.audit.models import StaffNotification

            membership = getattr(request, "tenant_membership", None)
            if membership is None:
                messages.error(request, "This account does not have a staff notification inbox for this business.")
            else:
                photo_path = reverse("console-org-menu-item-photo", kwargs={"item_id": item.pk})
                StaffNotification.objects.update_or_create(
                    tenant=request.tenant,
                    recipient=membership,
                    source_type="product_photo",
                    source_id=str(item.pk),
                    defaults={
                        "priority": "normal",
                        "title": f"Add photo · {item.name}",
                        "body": "Open this on your phone to take or upload the product photo.",
                        "url": photo_path,
                        "active": True,
                        "read_at": None,
                    },
                )
                messages.success(request, "Photo request sent to your account notifications.")
            return redirect("console-org-menu-item-edit", item_id=item.pk)

        class ProductPhotoForm(forms.Form):
            photo = forms.ImageField(
                widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})
            )
            def clean_photo(self):
                photo = self.cleaned_data["photo"]
                if photo.size > 5 * 1024 * 1024:
                    raise forms.ValidationError("Use an image smaller than 5 MB.")
                if getattr(photo, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
                    raise forms.ValidationError("Use JPEG, PNG or WebP.")
                return photo

        if request.POST.get("action") == "remove_photo":
            with transaction.atomic():
                item = MenuItem.objects.select_for_update().get(pk=item.pk, tenant=request.tenant)
                if item.product_image:
                    item.product_image = ""
                    item.save(update_fields=["product_image", "updated_at"])
                    messages.success(request, "Uploaded photo removed. The product can remain without a photo.")
            return redirect("console-org-menu-item-photo", item_id=item.pk)

        form = ProductPhotoForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                item = MenuItem.objects.select_for_update().get(pk=item.pk, tenant=request.tenant)
                item.product_image = form.cleaned_data["photo"]
                item.save(update_fields=["product_image", "updated_at"])
                from apps.audit.models import StaffNotification
                membership = getattr(request, "tenant_membership", None)
                if membership is not None:
                    StaffNotification.objects.filter(
                        tenant=request.tenant,
                        recipient=membership,
                        source_type="product_photo",
                        source_id=str(item.pk),
                    ).update(active=False)
            messages.success(request, "Photo saved. The desktop editor will show it shortly.")
            return redirect("console-org-menu-item-photo", item_id=item.pk)
        return render(request, self.template_name, {"item": item, "photo_form": form}, status=400)


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
        price_override = form.cleaned_data.get("price_override")
        link = MenuItemOutlet.objects.create(
            menu_item=self.menu_item,
            outlet=outlet,
            price_override=price_override,
        )
        if price_override is not None:
            log_audit(
                tenant_id=self.request.tenant.pk,
                user_id=self.request.user.pk,
                action="catalog.outlet_price_override_changed",
                entity_type="menu_item_outlet",
                entity_id=str(link.pk),
                payload={
                    "menu_item_id": str(self.menu_item.pk),
                    "item_name": self.menu_item.name,
                    "outlet_id": str(outlet.pk),
                    "outlet_name": outlet.name,
                    "before": str(self.menu_item.unit_price),
                    "after": str(price_override),
                    "override_before": None,
                    "override_after": str(price_override),
                },
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
        previous = MenuItemOutlet.objects.get(pk=self.object.pk).price_override
        response = super().form_valid(form)
        current = self.object.price_override
        if previous != current:
            log_audit(
                tenant_id=self.request.tenant.pk,
                user_id=self.request.user.pk,
                action="catalog.outlet_price_override_changed",
                entity_type="menu_item_outlet",
                entity_id=str(self.object.pk),
                payload={
                    "menu_item_id": str(self.menu_item.pk),
                    "item_name": self.menu_item.name,
                    "outlet_id": str(self.object.outlet_id),
                    "outlet_name": self.object.outlet.name,
                    "before": str(previous if previous is not None else self.menu_item.unit_price),
                    "after": str(current if current is not None else self.menu_item.unit_price),
                    "override_before": str(previous) if previous is not None else None,
                    "override_after": str(current) if current is not None else None,
                },
            )
        messages.success(self.request, "Outlet pricing updated.")
        return response

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

    def form_valid(self, form):
        obj = self.object
        name = obj.outlet.name
        override = obj.price_override
        outlet_id = obj.outlet_id
        link_id = obj.pk
        response = super().form_valid(form)
        if override is not None:
            remaining_links = MenuItemOutlet.objects.filter(menu_item=self.menu_item).exists()
            after_value = (
                str(self.menu_item.unit_price)
                if not remaining_links
                else "not offered at this sales area"
            )
            log_audit(
                tenant_id=self.request.tenant.pk,
                user_id=self.request.user.pk,
                action="catalog.outlet_price_override_changed",
                entity_type="menu_item_outlet",
                entity_id=str(link_id),
                payload={
                    "menu_item_id": str(self.menu_item.pk),
                    "item_name": self.menu_item.name,
                    "outlet_id": str(outlet_id),
                    "outlet_name": name,
                    "before": str(override),
                    "after": after_value,
                    "override_before": str(override),
                    "override_after": None,
                    "link_removed": True,
                },
            )
        messages.success(self.request, f"Removed outlet link for “{name}”.")
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgRetailAssemblyListView(RetailMerchandiseRequiredMixin, MenuItemScopedMixin, ListView):
    template_name = "console/org/retail_assembly_list.html"
    context_object_name = "components"

    def get_queryset(self):
        return RetailAssemblyComponent.objects.filter(
            tenant=self.request.tenant,
            parent_item=self.menu_item,
        ).select_related("component_item").order_by("component_item__name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        return ctx


class OrgRetailAssemblyCreateView(RetailMerchandiseRequiredMixin, MenuItemScopedMixin, CreateView):
    model = RetailAssemblyComponent
    form_class = ConsoleRetailAssemblyComponentForm
    template_name = "console/org/retail_assembly_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not self.menu_item.track_inventory:
            messages.error(request, "Enable stock tracking on the finished product before configuring an assembly.")
            return redirect("console-org-menu-item-edit", item_id=self.menu_item.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["parent_item"] = self.menu_item
        kw["tenant"] = self.request.tenant
        return kw

    def get_success_url(self):
        return reverse("console-org-menu-item-assembly", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.tenant = self.request.tenant
        obj.parent_item = self.menu_item
        try:
            obj.full_clean()
            obj.save()
        except IntegrityError:
            form.add_error("component_item", "That component is already in this assembly.")
            return self.form_invalid(form)
        messages.success(self.request, f"Component “{obj.component_item.name}” added.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        ctx["form_title"] = "Add assembly component"
        return ctx


class OrgRetailAssemblyUpdateView(RetailMerchandiseRequiredMixin, MenuItemScopedMixin, UpdateView):
    model = RetailAssemblyComponent
    form_class = ConsoleRetailAssemblyComponentForm
    template_name = "console/org/retail_assembly_form.html"
    pk_url_kwarg = "component_id"

    def get_queryset(self):
        return RetailAssemblyComponent.objects.filter(
            tenant=self.request.tenant,
            parent_item=self.menu_item,
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["parent_item"] = self.menu_item
        kw["tenant"] = self.request.tenant
        return kw

    def get_success_url(self):
        return reverse("console-org-menu-item-assembly", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.tenant = self.request.tenant
        obj.parent_item = self.menu_item
        obj.full_clean()
        obj.save()
        messages.success(self.request, "Assembly component updated.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["menu_item"] = self.menu_item
        ctx["form_title"] = f"Edit · {self.object.component_item.name}"
        return ctx


class OrgRetailAssemblyDeleteView(RetailMerchandiseRequiredMixin, MenuItemScopedMixin, DeleteView):
    model = RetailAssemblyComponent
    template_name = "console/org/retail_assembly_confirm_delete.html"
    pk_url_kwarg = "component_id"

    def get_queryset(self):
        return RetailAssemblyComponent.objects.filter(
            tenant=self.request.tenant,
            parent_item=self.menu_item,
        )

    def get_success_url(self):
        return reverse("console-org-menu-item-assembly", kwargs={"item_id": self.menu_item.pk})

    def form_valid(self, form):
        name = self.object.component_item.name
        response = super().form_valid(form)
        messages.success(self.request, f"Removed “{name}” from the assembly.")
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
