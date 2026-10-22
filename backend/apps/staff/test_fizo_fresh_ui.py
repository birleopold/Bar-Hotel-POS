"""Fresh redesign contract: rejected files must not reappear in the shared UI."""
from pathlib import Path

from django.test import SimpleTestCase


class FizoFreshShellTests(SimpleTestCase):
    def test_legacy_assets_are_deleted(self):
        app = Path(__file__).resolve().parent
        for rel in (
            "static/staff/staff-theme.css",
            "static/staff/staff-command.css",
            "static/staff/staff-density.css",
            "static/staff/fizo-retail-owner.css",
            "static/staff/fizo-floor-dashboard.css",
            "templates/staff/includes/workbench_sidebar.html",
        ):
            with self.subTest(path=rel):
                self.assertFalse((app / rel).exists())

    def test_shared_shell_uses_new_design_only(self):
        app = Path(__file__).resolve().parent
        base = (app / "templates/staff/base.html").read_text(encoding="utf-8")
        sidebar = (app / "templates/staff/includes/sidebar.html").read_text(encoding="utf-8")
        nav = (app / "templates/staff/includes/nav.html").read_text(encoding="utf-8")
        self.assertIn("fizo-fresh.css", base)
        self.assertIn("fz-nav", sidebar)
        self.assertIn("fz-top-title", nav)
        for text in (base, sidebar, nav):
            for forbidden in (
                "staff-theme.css", "staff-command.css", "staff-density.css",
                "fizo-retail-owner.css", "workbench_sidebar.html",
            ):
                self.assertNotIn(forbidden, text)
