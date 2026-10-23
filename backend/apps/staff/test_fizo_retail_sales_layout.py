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
        self.assertIn("staff/retail-workflows.css", page)
        self.assertNotIn("fizo-retail-sales.css", page)
        self.assertIn('staff_product.business_key == "retail"', landing)
        self.assertIn('Retail{% else %}Supermarket{% endif %} / Cashier', landing)
        self.assertNotIn('Fizo / Supermarket / Cashier', landing)
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
        self.assertTrue((root / "static/staff/retail-workflows.css").exists())


    def test_retail_dashboard_has_independent_business_heading(self):
        root = Path(__file__).resolve().parent
        dashboard = (root / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('staff_product.business_key == "supermarket" %}Supermarket dashboard', dashboard)
        self.assertIn('staff_product.business_key == "retail" %}Retail dashboard', dashboard)
        self.assertNotIn('staff_product.business_key == "supermarket" or staff_product.business_key == "retail" %}Supermarket dashboard', dashboard)
        get_template("staff/dashboard.html")

    def test_all_register_view_selection_uses_retail_outlet_types(self):
        root = Path(__file__).resolve().parent
        source = (root / "views_ops.py").read_text(encoding="utf-8")
        self.assertIn("visible_outlets = list(ctx[\"outlets\"])", source)
        self.assertIn("all(item.outlet_type in retail_types for item in visible_outlets)", source)
        self.assertIn('ctx["show_supermarket_lane"] = supermarket_lane', source)
        self.assertIn('ctx["show_retail_catalogue"]', source)
        self.assertIn("all(item.outlet_type in retail_types for item in outlets)", source)


    def test_retail_active_baskets_are_resume_cards(self):
        root = Path(__file__).resolve().parent
        lanes = (root / "templates/staff/includes/orders_lanes.html").read_text(encoding="utf-8")
        self.assertIn("{% if show_supermarket_lane %}", lanes)
        self.assertIn("fizo-active-sales", lanes)
        self.assertIn("Resume sale", lanes)
        self.assertIn("Resume basket", lanes)
        self.assertIn("staff-order-detail", lanes)
        self.assertIn("{% else %}", lanes)
