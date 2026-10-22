"""Source contract for Fizo stock balance page; separate from end-to-end acceptance."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse


class FizoStockPageTests(SimpleTestCase):
    def test_stock_template_compiles_and_routes_exist(self):
        get_template("staff/inventory/balances.html")
        for name in ("staff-inventory-balances", "staff-inventory-batches",
                     "staff-inventory-movement-create", "staff-inventory-transfer"):
            with self.subTest(route=name):
                self.assertTrue(reverse(name).startswith("/staff/"))

    def test_stock_controls_and_permission_gates_retained(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/inventory/balances.html").read_text(encoding="utf-8")
        for marker in ('fizo-stock__table', 'name="q"', 'name="low_stock"',
                       "stock_q", "low_stock", "balances", "b.quantity",
                       "b.outlet.name", "b.menu_item.name", "can_modify_inventory",
                       "page_obj.has_next"):
            with self.subTest(marker=marker):
                self.assertIn(marker, page)
        self.assertNotIn("staff-page-hero", page)
        self.assertEqual(page.count("{% block "), page.count("{% endblock %}"))
        self.assertTrue((root / "static/staff/fizo-stock.css").exists())
