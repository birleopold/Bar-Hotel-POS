"""Approved grocery cashier layout source contracts; no live transaction performed."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template

class FizoRetailCheckoutApprovedTests(SimpleTestCase):
    def test_checkout_templates_compile(self):
        for name in ("staff/order_detail_supermarket.html","staff/order_detail.html","staff/includes/fizo_pos_catalogue.html"):
            with self.subTest(name=name):
                get_template(name)

    def test_existing_order_forms_and_basket_remain(self):
        root=Path(__file__).resolve().parent
        parent=(root/"templates/staff/order_detail.html").read_text(encoding="utf-8")
        retail=(root/"templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        cards=(root/"templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        self.assertIn("fizo-checkout-catalogue",parent)
        self.assertIn("fizo-checkout-basket",parent)
        self.assertIn('value="record_payment"',parent)
        self.assertIn('value="scan_add_line"',retail)
        self.assertIn("retail-fast-checkout",retail)
        self.assertIn('event.key === "F3"',retail)
        self.assertIn("staff-orders",retail)
        self.assertIn("data-pos-menu-tile",cards)
        self.assertIn('value="add_line"',cards)
        self.assertIn("data-fizo-add-line-form",cards)
        self.assertIn("{% csrf_token %}",cards)
        self.assertIn("{% csrf_token %}",retail)
        self.assertIn("{% if is_supermarket_outlet %}",parent)

    def test_visual_basket_keeps_authorized_stock_updates(self):
        root = Path(__file__).resolve().parent
        page = (root/"templates/staff/order_detail.html").read_text(encoding="utf-8")
        retail = (root/"templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn("fizo-retail-basket-row", page)
        self.assertIn("data-fizo-qty-form", page)
        self.assertIn('value="adjust_line_qty"', page)
        self.assertIn('value="void_line"', page)
        self.assertIn('name="reason"', page)
        self.assertIn("{% csrf_token %}", page)
        self.assertIn("data-fizo-step", retail)
        self.assertIn("form.requestSubmit()", retail)


    def test_checkout_entry_is_non_mutating_and_payment_quick_choices(self):
        from django.urls import reverse, resolve
        self.assertEqual(resolve(reverse("staff-retail-pos-entry")).url_name, "staff-retail-pos-entry")
        root = Path(__file__).resolve().parent
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        marker = view.split("class StaffRetailPosEntryView(", 1)[1].split("class StaffOrderQuickCreateView(", 1)[0]
        self.assertIn("PosShiftStatus.OPEN", marker)
        self.assertIn("created_by=request.user", marker)
        self.assertIn('redirect("staff-order-detail"', marker)
        self.assertNotIn("create_order_with_lines(", marker)
        sidebar = (root/"templates/staff/includes/sidebar.html").read_text(encoding="utf-8")
        self.assertIn("staff-retail-pos-entry", sidebar)
        self.assertIn("Sales</a>", sidebar)
        detail = (root/"templates/staff/order_detail.html").read_text(encoding="utf-8")
        for value in ("cash", "card", "mobile_money"):
            self.assertIn('data-fizo-payment-method="' + value + '"', detail)
        retail = (root/"templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn("method.dispatchEvent", retail)
        self.assertIn("data-fizo-payment-method", retail)


    def test_basket_totals_are_server_rendered_and_only_retail_style_applies(self):
        root = Path(__file__).resolve().parent
        page = (root/"templates/staff/order_detail.html").read_text(encoding="utf-8")
        css = (root/"static/staff/fizo-checkout-v1.css").read_text(encoding="utf-8")
        self.assertIn("fizo-retail-basket-summary", page)
        self.assertIn("{{ order.subtotal }}", page)
        self.assertIn("{{ order.tax_total }}", page)
        self.assertIn("{{ balance_due }}", page)
        self.assertIn(".staff-main:has(.fizo-checkout-catalogue)", css)
        catalogue = (root/"templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        self.assertIn("Add to basket", catalogue)


    def test_dedicated_checkout_start_uses_safe_post(self):
        from django.template.loader import get_template
        get_template("staff/retail_pos_start.html")
        root = Path(__file__).resolve().parent
        page = (root/"templates/staff/retail_pos_start.html").read_text(encoding="utf-8")
        self.assertIn('method="post"', page)
        self.assertIn("staff-order-quick-create", page)
        self.assertIn("{% csrf_token %}", page)
        self.assertIn("current_shift", page)
        view = (root/"views_ops.py").read_text(encoding="utf-8")
        entry = view.split("class StaffRetailPosEntryView(", 1)[1].split("class StaffOrderQuickCreateView(", 1)[0]
        self.assertIn('render(request, "staff/retail_pos_start.html"', entry)
        self.assertNotIn("create_order_with_lines(", entry)

    def test_search_uses_real_sku_and_barcode_and_shortcuts_use_existing_routes(self):
        root = Path(__file__).resolve().parent
        catalogue = (root/"templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        detail = (root/"templates/staff/order_detail.html").read_text(encoding="utf-8")
        for token in ("data-item-sku", "data-item-barcode", "data-fizo-search-clear"):
            self.assertIn(token, catalogue)
        for token in ("tile.dataset.itemSku", "tile.dataset.itemBarcode",
                      "fizo-retail-basket-tools", "staff-order-print", 'href="#hold_label"'):
            self.assertIn(token, detail)

    def test_popular_item_shortcuts_are_scoped_and_use_existing_tile_flow(self):
        root = Path(__file__).resolve().parent
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        template = (root / "templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        checkout = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        for key in ("retail_quick_pick_ids", "order__tenant_id=order.tenant_id",
                    "order__outlet_id=order.outlet_id", "order__is_paid=True",
                    "is_voided=False", "available_ids"):
            self.assertIn(key, view)
        self.assertIn("data-fizo-quick-pick", template)
        self.assertIn("data-fizo-favourites", template)
        self.assertIn("tile.click()", checkout)


    def test_catalogue_progressive_rendering_preserves_all_search_matches(self):
        root = Path(__file__).resolve().parent
        catalogue = (root/"templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        detail = (root/"templates/staff/order_detail.html").read_text(encoding="utf-8")
        self.assertIn("data-fizo-page-controls", catalogue)
        self.assertIn("data-fizo-load-more", catalogue)
        self.assertIn("pageSize = browser.querySelector", detail)
        self.assertIn("pageLimit += pageSize", detail)
        self.assertIn("matchesCategory && matchesSearch", detail)
        self.assertIn("found += 1", detail)


    def test_server_catalogue_is_bounded_without_weakening_post_validation(self):
        root = Path(__file__).resolve().parent
        view = (root/"views_ops.py").read_text(encoding="utf-8")
        template = (root/"templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        self.assertIn('self.request.GET.get("catalogue_q")', view)
        self.assertIn("menu_qs = list(menu_qs[:81])", view)
        self.assertIn('self.request.method == "GET"', view)
        self.assertIn("ctx[\"add_line_form\"].fields[\"menu_item\"].queryset", view)
        self.assertIn('name="catalogue_q"', template)
        self.assertIn("No matching products", template)
        self.assertIn("retail_catalogue_has_more", template)
