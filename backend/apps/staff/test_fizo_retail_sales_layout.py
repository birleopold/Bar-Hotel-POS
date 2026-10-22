"""Retail cashier sales landing regression contract; browser acceptance separate."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse

class RetailSalesLandingTests(SimpleTestCase):
    def test_templates_parse_and_routes_resolve(self):
        get_template("staff/orders_list.html")
        get_template("staff/includes/fizo_retail_sales_landing.html")
        for route in ("staff-orders", "staff-order-quick-create", "staff-pos-shifts"):
            self.assertTrue(reverse(route).startswith("/staff/"))

    def test_checkout_requires_shift_and_preserves_existing_order_flows(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/orders_list.html").read_text(encoding="utf-8")
        landing = (root / "templates/staff/includes/fizo_retail_sales_landing.html").read_text(encoding="utf-8")
        self.assertIn("{% if show_supermarket_lane %}", page)
        self.assertIn("fizo-retail-sales.css", page)
        self.assertIn("supermarket_shift_open", landing)
        self.assertIn("current_outlet", landing)
        self.assertIn("staff-order-quick-create", landing)
        self.assertIn("staff/includes/orders_lanes.html", landing)
        self.assertIn('name="mode" value="hold"', landing)
        self.assertIn("staff-order-detail", landing)
        self.assertIn("returns_task", landing)
        self.assertIn("page_obj.has_next", landing)
        self.assertIn("{% csrf_token %}", landing)
        self.assertEqual(page.count("{% block "), page.count("{% endblock %}"))
        self.assertTrue((root / "static/staff/fizo-retail-sales.css").exists())
