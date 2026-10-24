"""Supermarket product table: source contract, not browser acceptance."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse


class FizoRetailProductsLayoutTests(SimpleTestCase):
    def test_checkout_start_distinguishes_missing_register_from_closed_shift(self):
        page = (Path(__file__).resolve().parent / "templates/staff/includes/fizo_retail_sales_landing.html").read_text(encoding="utf-8")
        self.assertIn("{% elif not current_outlet %}", page)
        self.assertIn("Select register", page)
        self.assertIn("{% if not current_outlet %}Select register{% elif supermarket_shift_open %}Manage open shift{% else %}Open register{% endif %}", page)
        self.assertIn("{% elif not supermarket_shift_open %}", page)
        self.assertIn("Open shift first", page)

    def test_paid_sale_next_customer_uses_server_idempotency(self):
        root = Path(__file__).resolve().parent
        template = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        views = (root / "views_ops.py").read_text(encoding="utf-8")
        self.assertIn('name="quick_create_key" value="{{ next_sale_request_key }}"', template)
        self.assertIn("this.dataset.submitting = '1'", template)
        self.assertIn('ctx["next_sale_request_key"] = uuid.uuid4()', views)

    def test_cashier_new_and_held_basket_forms_block_double_submit(self):
        page = (Path(__file__).resolve().parent / "templates/staff/includes/fizo_retail_sales_landing.html").read_text(encoding="utf-8")
        self.assertEqual(page.count("this.dataset.submitting = '1'"), 2)
        self.assertEqual(page.count("this.querySelector('button[type=submit]').disabled = true"), 2)
        self.assertIn('name="mode" value="hold"', page)

    def test_cashier_sales_landing_has_real_hold_basket_action(self):
        page = (Path(__file__).resolve().parent / "templates/staff/includes/fizo_retail_sales_landing.html").read_text(encoding="utf-8")
        self.assertIn("Hold basket</button>", page)
        self.assertIn('name="mode" value="hold"', page)
        self.assertIn("staff-order-quick-create", page)
        self.assertIn("{% csrf_token %}", page)
        get_template("staff/includes/fizo_retail_sales_landing.html")

    def test_catalogue_route_and_template_compile(self):
        self.assertTrue(reverse("staff-menu").startswith("/staff/"))
        self.assertTrue(reverse("console-org-menu-item-create").startswith("/console/"))
        self.assertTrue(reverse("console-org-catalog-import").startswith("/console/"))
        get_template("staff/menu_list.html")

    def test_retail_branch_has_real_product_data_and_actions(self):
        root = Path(__file__).resolve().parent
        s = (root / "templates/staff/menu_list.html").read_text(encoding="utf-8")
        self.assertIn("{% if show_retail_catalogue %}", s)
        self.assertIn("fizo-retail-products.css", s)
        self.assertIn("fizo-products__table", s)
        self.assertIn("cat.items.all", s)
        self.assertIn("item.product_image_src", s)
        self.assertIn("item.unit_price", s)
        self.assertIn('name="q"', s)
        self.assertIn('value="display_details"', s)
        self.assertIn("{% csrf_token %}", s)
        self.assertIn("can_manage_tv_details", s)
        self.assertIn("staff_nav.workspace", s)
        self.assertEqual(s.count("{% block "), s.count("{% endblock %}"))

    def test_product_photo_upload_contract_spans_form_and_both_displays(self):
        root = Path(__file__).resolve().parents[1]
        editor = (root / "console/templates/console/org/menu_item_form.html").read_text(encoding="utf-8")
        checkout = (Path(__file__).resolve().parent / "templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        self.assertIn('enctype="multipart/form-data"', editor)
        self.assertIn("object.product_image_src", editor)
        self.assertIn("item.product_image_src", checkout)
        self.assertIn("item.product_image_src", (Path(__file__).resolve().parent / "templates/staff/menu_list.html").read_text(encoding="utf-8"))
        get_template("console/org/menu_item_form.html")
        get_template("staff/includes/fizo_pos_catalogue.html")

    def test_desktop_product_save_preserves_parallel_phone_photo(self):
        source = (Path(__file__).resolve().parents[1] / "console/views_catalog.py").read_text(encoding="utf-8")
        self.assertIn('elif "product_image" not in form.changed_data:', source)
        self.assertIn("instance.product_image = current.product_image", source)
        self.assertIn("pk=view.object.pk, tenant=view.request.tenant", source)

    def test_phone_photo_writes_are_atomic(self):
        source = (Path(__file__).resolve().parents[1] / "console/views_catalog.py").read_text(encoding="utf-8")
        self.assertIn("select_for_update()", source)
        self.assertIn("with transaction.atomic():", source)

    def test_phone_photo_can_be_removed_without_deleting_product(self):
        root = Path(__file__).resolve().parents[1] / "console"
        page = (root / "templates/console/org/menu_item_photo.html").read_text(encoding="utf-8")
        handler = (root / "views_catalog.py").read_text(encoding="utf-8")
        self.assertIn('name="action" value="remove_photo"', page)
        self.assertIn("{% if item.product_image %}", page)
        self.assertIn('request.POST.get("action") == "remove_photo"', handler)
        self.assertIn('item.save(update_fields=["product_image", "updated_at"])', handler)
        get_template("console/org/menu_item_photo.html")

    def test_phone_photo_sync_has_manual_recovery_and_login_feedback(self):
        root = Path(__file__).resolve().parents[1] / "console/templates/console/org"
        page = (root / "menu_item_form.html").read_text(encoding="utf-8")
        self.assertIn("data-refresh-phone-photo", page)
        self.assertIn('refresh.addEventListener("click", checkPhoto)', page)
        self.assertIn("Confirm you are still signed in", page)
        self.assertIn('aria-live="polite"', page)
        get_template("console/org/menu_item_form.html")

    def test_desktop_photo_sync_tracks_effective_image_url(self):
        root = Path(__file__).resolve().parents[1] / "console/templates/console/org"
        source = (root / "menu_item_form.html").read_text(encoding="utf-8")
        self.assertIn('var known = "{{ object.product_image_src|escapejs }}";', source)
        self.assertIn("if (data.image_url === known) return;", source)
        self.assertIn("known = data.image_url;", source)
        self.assertIn('credentials: "same-origin"', source)

    def test_imported_products_can_receive_optional_photos_later(self):
        root = Path(__file__).resolve().parents[1] / "console/templates/console/org"
        imported = (root / "catalog_import.html").read_text(encoding="utf-8")
        listing = (root / "menu_item_list.html").read_text(encoding="utf-8")
        self.assertIn("Photos are optional.", imported)
        self.assertIn("Copy phone link", imported)
        self.assertIn("Add photo", listing)
        self.assertIn("console-org-menu-item-photo", listing)
        get_template("console/org/catalog_import.html")

    def test_independent_stylesheet_exists(self):
        root = Path(__file__).resolve().parent
        self.assertTrue((root / "static/staff/fizo-retail-products.css").is_file())
