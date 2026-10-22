"""Inventory Fizo screen contracts. Browser and DB flows require separate acceptance."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse

class FizoInventoryWorkflowTests(SimpleTestCase):
    def test_three_individual_pages_compile(self):
        for name in ("movements.html", "batches.html", "movement_form.html"):
            with self.subTest(name=name):
                get_template("staff/inventory/" + name)
        for route in ("staff-inventory-movements", "staff-inventory-batches",
                      "staff-inventory-movement-create", "staff-inventory-movement-upload"):
            self.assertTrue(reverse(route).startswith("/staff/"))

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
