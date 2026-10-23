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
    def test_required_stylesheets_exist(self):
        for name in ("fizo-fresh.css", "retail-cashier.css", "retail-workflows.css", "fizo-hospitality-pos.css"):
            with self.subTest(stylesheet=name):
                self.assertTrue((STATIC / name).is_file())

    def test_removed_retail_stylesheets_stay_removed(self):
        for name in ("fizo-checkout-v1.css", "reference-locked-checkout.css",
                     "retail-counter-v2.css", "fizo-retail-sales.css"):
            with self.subTest(stylesheet=name):
                self.assertFalse((STATIC / name).exists())

    def test_supermarket_inherits_retail_workflows_before_cashier_override(self):
        parent = (TEMPLATES / "order_detail.html").read_text(encoding="utf-8")
        child = (TEMPLATES / "order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn("retail-workflows.css", parent)
        self.assertIn("{{ block.super }}", child)
        self.assertIn("retail-cashier.css", child)

    def test_retail_sales_start_loads_consolidated_styles(self):
        page = (TEMPLATES / "retail_pos_start.html").read_text(encoding="utf-8")
        self.assertIn("retail-workflows.css", page)

    def test_no_removed_stylesheet_references_in_staff_templates(self):
        retired = ("fizo-checkout-v1.css", "reference-locked-checkout.css",
                   "retail-counter-v2.css", "fizo-retail-sales.css")
        for template in TEMPLATES.rglob("*.html"):
            source = template.read_text(encoding="utf-8")
            for name in retired:
                with self.subTest(template=str(template), retired=name):
                    self.assertNotIn(name, source)


if __name__ == "__main__":
    unittest.main()
