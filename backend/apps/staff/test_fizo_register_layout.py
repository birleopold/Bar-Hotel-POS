"""Fizo cashier shift and workstation template contracts (not browser acceptance)."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template

class FizoRegisterLayoutTests(SimpleTestCase):
    def test_templates_compile(self):
        for name in ("staff/pos_shifts.html", "staff/workstations.html"):
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

    def test_workstation_actions_and_permissions_retained(self):
        root = Path(__file__).resolve().parent
        station = (root / "templates/staff/workstations.html").read_text(encoding="utf-8")
        self.assertIn("fizo-register.css", station)
        self.assertIn("can_manage", station)
        self.assertIn('value="forget"', station)
        self.assertEqual(station.count("<form "), station.count("{% csrf_token %}"))
        self.assertTrue((root / "static/staff/fizo-register.css").is_file())
