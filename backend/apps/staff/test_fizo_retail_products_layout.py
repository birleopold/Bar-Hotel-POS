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
        self.assertIn("{% if grocery_owner_shell %}", s)
        self.assertIn("fizo-retail-products.css", s)
        self.assertIn("fizo-products__table", s)
        self.assertIn("cat.items.all", s)
        self.assertIn("item.display_image_url", s)
        self.assertIn("item.unit_price", s)
        self.assertIn('name="q"', s)
        self.assertIn('value="display_details"', s)
        self.assertIn("{% csrf_token %}", s)
        self.assertIn("can_manage_tv_details", s)
        self.assertIn("staff_nav.workspace", s)
        self.assertEqual(s.count("{% block "), s.count("{% endblock %}"))

    def test_independent_stylesheet_exists(self):
        root = Path(__file__).resolve().parent
        self.assertTrue((root / "static/staff/fizo-retail-products.css").is_file())
