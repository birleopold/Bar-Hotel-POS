"""Guard against restoring the retired Fizo operations dashboard template."""
from pathlib import Path

from django.test import SimpleTestCase


class FizoDashboardStructureTests(SimpleTestCase):
    def test_dashboard_uses_new_page_and_retired_layout_is_absent(self):
        root = Path(__file__).resolve().parent
        markup = (root / "templates" / "staff" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('retail-workflows.css', markup)
        self.assertIn('class="fizo-dash"', markup)
        self.assertIn("staff_dashboard_sales_snapshot", markup)
        self.assertIn("staff_dashboard_lodging_snapshot", markup)
        self.assertIn("staff_dashboard_primary_actions", markup)
        self.assertNotIn("staff-dash-hero--modern", markup)
        self.assertNotIn("staff-tile-grid", markup)
        self.assertNotIn("grocery_owner_setup_styles.html", markup)

    def test_sector_dashboard_css_exists(self):
        root = Path(__file__).resolve().parent
        stylesheet = root / "static" / "staff" / "retail-workflows.css"
        self.assertTrue(stylesheet.is_file())
        self.assertIn(".fizo-dash__kpis", stylesheet.read_text(encoding="utf-8"))
