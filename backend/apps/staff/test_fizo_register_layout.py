"""Fizo cashier shift and workstation template contracts (not browser acceptance)."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template

class FizoRegisterLayoutTests(SimpleTestCase):
    def test_templates_compile(self):
        for name in ("staff/pos_shifts.html", "staff/pos_shift_detail.html", "staff/workstations.html"):
            with self.subTest(name=name):
                get_template(name)

    def test_shift_actions_and_csrf_retained(self):
        root = Path(__file__).resolve().parent
        shift = (root / "templates/staff/pos_shifts.html").read_text(encoding="utf-8")
        self.assertIn("fizo-register.css", shift)
        self.assertIn("open_shift", shift)
        self.assertIn("selected_station", shift)
        self.assertEqual(shift.count("<form "), shift.count("{% csrf_token %}"))
        self.assertEqual(shift.count("{% block "), shift.count("{% endblock %}"))

    def test_shift_uses_register_styles_even_without_grocery_owner_shell(self):
        root = Path(__file__).resolve().parent
        shift = (root / "templates/staff/pos_shifts.html").read_text(encoding="utf-8")
        self.assertIn("staff-main--wide fizo-register-page", shift)
        self.assertIn("fizo-register.css", shift)
        self.assertIn("fizo-register__history", shift)
        self.assertIn("fizo-register__tablewrap", shift)
        # In particular the register stylesheet cannot depend on the shell branch.
        self.assertNotIn("{% if grocery_owner_shell %}<link rel=\"stylesheet\"", shift)
        self.assertEqual(shift.count("<section"), shift.count("</section>"))

    def test_manager_shift_review_route_and_evidence_surface(self):
        root = Path(__file__).resolve().parent
        urls = (root / "urls.py").read_text(encoding="utf-8")
        views = (root / "views_ops.py").read_text(encoding="utf-8")
        shifts = (root / "templates/staff/pos_shifts.html").read_text(encoding="utf-8")
        detail = (root / "templates/staff/pos_shift_detail.html").read_text(encoding="utf-8")
        self.assertIn('name="staff-pos-shift-detail"', urls)
        self.assertIn("class StaffPosShiftDetailView", views)
        self.assertIn('ctx["can_review_shift_history"] = manager', views)
        self.assertIn("build_shift_reconciliation(shift)", views)
        self.assertIn("shift_cash_snapshot(shift=shift)", views)
        self.assertIn("{% if can_review_shift_history %}", shifts)
        self.assertIn("{% url 'staff-pos-shift-detail' s.pk %}", shifts)
        self.assertIn("Tender reconciliation", detail)
        self.assertIn("Drawer movements", detail)
        self.assertIn("Recent payments", detail)
        self.assertIn("Recent refunds", detail)
        self.assertIn("Handover evidence", detail)

    def test_workstation_actions_and_permissions_retained(self):
        root = Path(__file__).resolve().parent
        station = (root / "templates/staff/workstations.html").read_text(encoding="utf-8")
        self.assertIn("fizo-register.css", station)
        self.assertIn("can_manage", station)
        self.assertIn('value="forget"', station)
        self.assertEqual(station.count("<form "), station.count("{% csrf_token %}"))
        self.assertTrue((root / "static/staff/fizo-register.css").is_file())
