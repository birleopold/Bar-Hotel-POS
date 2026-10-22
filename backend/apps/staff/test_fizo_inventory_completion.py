"""Compile all inventory templates and guard selected stock forms.
This is a source/template contract, not an end-to-end stock adjustment test.
"""
from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase


class FizoInventoryCompletionTests(SimpleTestCase):
    names = (
        "balances.html", "batches.html", "count_create.html", "count_detail.html",
        "counts_list.html", "includes/subnav.html", "intelligence.html",
        "movement_form.html", "movement_upload.html", "movements.html",
        "scale_labels.html", "shelves.html", "transfer_form.html",
        "transfer_receipts.html",
    )

    def test_all_inventory_templates_compile(self):
        for name in self.names:
            with self.subTest(name=name):
                get_template("staff/inventory/" + name)

    def test_all_inventory_templates_have_fizo_page_structure(self):
        base = Path(__file__).resolve().parent / "templates/staff/inventory"
        for name in self.names:
            text = (base / name).read_text(encoding="utf-8")
            if name.startswith("includes/"):
                self.assertIn("fizo-inventory__tabs", text)
                continue
            with self.subTest(name=name):
                self.assertIn("fizo-", text)
                self.assertEqual(text.count("{% block "), text.count("{% endblock %}"))

    def test_import_and_label_workflows_keep_real_submit_controls(self):
        base = Path(__file__).resolve().parent / "templates/staff/inventory"
        upload = (base / "movement_upload.html").read_text(encoding="utf-8")
        self.assertIn('enctype="multipart/form-data"', upload)
        self.assertIn("staff-inventory-movement-upload-template", upload)
        self.assertIn("{% csrf_token %}", upload)
        shelf = (base / "shelves.html").read_text(encoding="utf-8")
        self.assertIn("can_assign_shelves", shelf)
        self.assertIn('name="aisle"', shelf)
        self.assertIn('name="shelf"', shelf)
        self.assertIn("{% csrf_token %}", shelf)
        scale = (base / "scale_labels.html").read_text(encoding="utf-8")
        self.assertIn("can_configure", scale)
        self.assertIn('name="scale_prefix"', scale)
        self.assertIn('name="scale_item_code"', scale)
        self.assertIn("{% csrf_token %}", scale)
        planning = (base / "intelligence.html").read_text(encoding="utf-8")
        self.assertIn('name="safety_days"', planning)
        self.assertIn("stock_rows", planning)
