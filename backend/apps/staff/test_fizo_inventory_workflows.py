"""Inventory Fizo screen contracts. Browser and DB flows require separate acceptance."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse

class FizoInventoryWorkflowTests(SimpleTestCase):
    def test_stock_balances_uses_canonical_inventory_css(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/inventory/balances.html").read_text(encoding="utf-8")
        styles = (root / "static/staff/fizo-inventory-workflows.css").read_text(encoding="utf-8")
        self.assertIn("fizo-inventory-workflows.css", page)
        self.assertNotIn("fizo-stock.css", page)
        self.assertIn(".fizo-stock", styles)
        self.assertFalse((root / "static/staff/fizo-stock.css").exists())
        get_template("staff/inventory/balances.html")

    def test_three_individual_pages_compile(self):
        for name in ("movements.html", "batches.html", "movement_form.html"):
            with self.subTest(name=name):
                get_template("staff/inventory/" + name)
        for route in ("staff-inventory-movements", "staff-inventory-batches",
                      "staff-inventory-movement-create", "staff-inventory-movement-upload"):
            self.assertTrue(reverse(route).startswith("/staff/"))

    def test_shared_inventory_pages_follow_active_business(self):
        root = Path(__file__).resolve().parent / "templates/staff/inventory"
        for name in ("balances.html", "batches.html", "intelligence.html", "movement_form.html", "movements.html", "movement_upload.html", "scale_labels.html", "shelves.html"):
            with self.subTest(name=name):
                source = (root / name).read_text(encoding="utf-8")
                self.assertIn('staff_product.workspace_label|default:"Business"', source)
                self.assertNotIn("Fizo / Supermarket / Inventory", source)
                get_template("staff/inventory/" + name)

    def test_real_transaction_controls_preserved(self):
        root = Path(__file__).resolve().parent
        directory = root / "templates/staff/inventory"
        for name in ("movements.html", "batches.html", "movement_form.html"):
            with self.subTest(name=name):
                text = (directory / name).read_text(encoding="utf-8")
                self.assertIn("fizo-inventory-workflows.css", text)
                self.assertIn("fizo-inventory__header", text)
                self.assertEqual(text.count("{% block "), text.count("{% endblock %}"))
        batches = (directory / "batches.html").read_text(encoding="utf-8")
        for action in ("receive_batch", "label_existing"):
            self.assertIn('value="' + action + '"', batches)
        self.assertIn("can_modify_inventory", batches)
        self.assertIn("batch_status", batches)
        self.assertIn("batch_query", batches)
        self.assertEqual(batches.count('<form '), batches.count('{% csrf_token %}') + 1)
        movement = (directory / "movement_form.html").read_text(encoding="utf-8")
        self.assertIn("{% for field in form %}", movement)
        self.assertIn('value="create_tracked_item"', movement)
        self.assertEqual(movement.count('<form '), movement.count('{% csrf_token %}'))
        self.assertTrue((root / "static/staff/fizo-inventory-workflows.css").exists())
