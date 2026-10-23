"""Regression checks for the unified Fizo retail CSS dependency contract.

These tests only validate repository asset wiring and intentional cascade order;
visual parity still requires real-browser screenshot comparisons.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates" / "staff"
STATIC = ROOT / "static" / "staff"


class UnifiedCssArchitectureTests(unittest.TestCase):
    def test_shared_dashboard_primitives_and_active_navigation(self):
        css = (STATIC / "fizo-fresh.css").read_text(encoding="utf-8")
        sidebar = (TEMPLATES / "includes" / "sidebar.html").read_text(encoding="utf-8")
        for token in (".fz-kpi-grid", ".fz-dashboard-panels",
                      ".fz-management-toolbar", ".fz-status",
                      ".fz-nav a[aria-current=\\\"page\\\"]"):
            with self.subTest(token=token):
                self.assertIn(token.replace('\\\"', '"'), css)
        for route in ("staff-inventory-balances", "staff-purchasing-orders",
                      "staff-lodging-reservations", "staff-lodging-housekeeping",
                      "staff-workspace-branding"):
            with self.subTest(route=route):
                self.assertIn("u == '" + route + "'", sidebar)

    def test_hotel_room_status_uses_shared_design_without_replacing_data(self):
        dashboard = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
        styles = (STATIC / "fizo-fresh.css").read_text(encoding="utf-8")
        self.assertIn("staff_dashboard_lodging_snapshot.ready_rooms", dashboard)
        self.assertIn("staff_dashboard_lodging_snapshot.dirty_rooms", dashboard)
        self.assertIn("staff_dashboard_lodging_snapshot.out_of_order_rooms", dashboard)
        self.assertIn(".fizo-dash__roomgrid>div:first-child", styles)
        self.assertIn(".fizo-dash__roomgrid>div:nth-child(2)", styles)
        self.assertIn(".fizo-dash__roomgrid>div:nth-child(3)", styles)

    def test_catalogues_load_unified_management_styles(self):
        page = (TEMPLATES / "menu_list.html").read_text(encoding="utf-8")
        css = (STATIC / "management-workflows.css").read_text(encoding="utf-8")
        self.assertIn("management-workflows.css", page)
        self.assertIn(".fizo-products", css)
        self.assertIn(".hospitality-workflow", css)

    def test_dashboard_uses_shared_foundation(self):
        dashboard = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
        core = (STATIC / "fizo-fresh.css").read_text(encoding="utf-8")
        self.assertNotIn("fizo-dashboard-v2.css", dashboard)
        self.assertIn(".fizo-dash__kpis", core)
        self.assertIn(".fizo-dash__roomgrid", core)

    def test_staff_static_stylesheet_references_resolve(self):
        """Every literal staff stylesheet URL in staff templates must exist."""
        pattern = re.compile(r"""\{%\s*static\s+['"]staff/([^'"]+\.css)['"]\s*%\}""")
        for template in TEMPLATES.rglob("*.html"):
            html = template.read_text(encoding="utf-8")
            for css_path in pattern.findall(html):
                with self.subTest(template=str(template), asset=css_path):
                    self.assertTrue((STATIC / css_path).is_file())

    def test_current_management_styles_do_not_reference_retired_assets(self):
        source = (TEMPLATES / "menu_list.html").read_text(encoding="utf-8")
        self.assertNotIn("fizo-retail-products.css", source)
        self.assertNotIn("hospitality-workflow.css", source)

    def test_required_stylesheets_exist(self):
        for name in ("fizo-fresh.css", "retail-cashier.css", "retail-workflows.css", "hospitality-workflows.css",
                     "management-workflows.css"):
            with self.subTest(stylesheet=name):
                self.assertTrue((STATIC / name).is_file())

    def test_removed_retail_stylesheets_stay_removed(self):
        for name in ("fizo-checkout-v1.css", "reference-locked-checkout.css",
                     "retail-counter-v2.css", "fizo-retail-sales.css",
                     "fizo-hospitality-pos.css", "fizo-dashboard-v2.css",
                     "fizo-retail-products.css", "hospitality-workflow.css"):
            with self.subTest(stylesheet=name):
                self.assertFalse((STATIC / name).exists())

    def test_supermarket_inherits_retail_workflows_before_cashier_override(self):
        parent = (TEMPLATES / "order_detail.html").read_text(encoding="utf-8")
        child = (TEMPLATES / "order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn("retail-workflows.css", parent)
        self.assertIn("{{ block.super }}", child)
        self.assertIn("retail-cashier.css", child)

    def test_hospitality_loads_only_for_non_supermarket_orders(self):
        page = (TEMPLATES / "order_detail.html").read_text(encoding="utf-8")
        self.assertIn("hospitality-workflows.css", page)
        self.assertIn("{% if is_supermarket_outlet %}", page)

    def test_retail_sales_start_loads_consolidated_styles(self):
        page = (TEMPLATES / "retail_pos_start.html").read_text(encoding="utf-8")
        self.assertIn("retail-workflows.css", page)

    def test_no_removed_stylesheet_references_in_staff_templates(self):
        retired = ("fizo-checkout-v1.css", "reference-locked-checkout.css",
                   "retail-counter-v2.css", "fizo-retail-sales.css",
                   "fizo-hospitality-pos.css", "fizo-dashboard-v2.css",
                   "fizo-retail-products.css", "hospitality-workflow.css")
        for template in TEMPLATES.rglob("*.html"):
            source = template.read_text(encoding="utf-8")
            for name in retired:
                with self.subTest(template=str(template), retired=name):
                    self.assertNotIn(name, source)


if __name__ == "__main__":
    unittest.main()
