"""Regression checks for real restaurant/bar ordering layout."""
from pathlib import Path
from django.test import SimpleTestCase

class FizoHospitalityPOSLayoutTests(SimpleTestCase):
    def test_table_transfer_keeps_operator_on_floor_view(self):
        source = (Path(__file__).resolve().parent / "views_ops.py").read_text(encoding="utf-8")
        transfer = source.split('elif action == "transfer_table":', 1)[1].split("else:", 1)[0]
        self.assertIn('messages.success(request, f"Check moved to {order.table_label}.")', transfer)
        self.assertIn('return redirect("staff-tables")', transfer)

    def test_order_has_new_menu_and_bill_panes(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        catalogue = (root / "templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        self.assertIn("hospitality-workflows.css", page)
        self.assertNotIn("hospitality-workflow.css", page)
        self.assertIn('class="fizo-hospitality-catalogue"', page)
        self.assertIn('class="fizo-hospitality-bill"', page)
        self.assertIn('name="action" value="record_payment"', page)
        self.assertIn('name="action" value="adjust_line_qty"', page)
        self.assertIn('name="action" value="add_line"', catalogue)
        self.assertIn("staff-pos-menu-browser", catalogue)
        self.assertEqual(page.count("{% if "), page.count("{% endif %}"))
    def test_stylesheet_exists(self):
        root = Path(__file__).resolve().parent
        self.assertTrue((root / "static/staff/hospitality-workflows.css").is_file())
