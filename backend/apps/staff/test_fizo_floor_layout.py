"""Ensure restaurant table configuration keeps the new Fizo UI, not the rejected theme."""
from pathlib import Path
from django.test import SimpleTestCase

class FizoFloorLayoutTests(SimpleTestCase):
    def test_floor_template_is_single_new_layout(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/tables_list.html").read_text(encoding="utf-8")
        self.assertEqual(page.count("{% block extra_css %}"), 1)
        self.assertIn("fizo-hospitality-floor.css", page)
        self.assertIn("fizo-floor__grid", page)
        self.assertIn("can_modify_tables", page)
        self.assertIn("staff-table-edit", page)
        self.assertNotIn("hospitality-workflow.css", page)
        self.assertNotIn("staff-pos-tables-grid", page)
    def test_page_css_is_present(self):
        root = Path(__file__).resolve().parent
        self.assertTrue((root / "static/staff/fizo-hospitality-floor.css").is_file())
