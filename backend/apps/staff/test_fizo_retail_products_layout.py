"""Supermarket product table: source contract, not browser acceptance."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse


class FizoRetailProductsLayoutTests(SimpleTestCase):
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
