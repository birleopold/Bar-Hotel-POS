"""Source-level contract for hotel reservation register (not browser acceptance)."""
from pathlib import Path

from django.test import SimpleTestCase


class FizoHotelReservationsLayoutTests(SimpleTestCase):
    def test_reservation_page_uses_new_shell_and_keeps_operations(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/reservations_list.html").read_text(encoding="utf-8")
        self.assertIn("fizo-hotel-frontdesk.css", page)
        self.assertNotIn("hospitality-workflow.css", page)
        self.assertIn("fizo-hotel__table", page)
        self.assertIn("staff-lodging-reservation-detail", page)
        self.assertIn("staff-lodging-reservation-create", page)
        self.assertIn("can_modify_lodging", page)
        self.assertIn("status_filter", page)
        self.assertIn("lane_filter", page)
        self.assertIn("page_obj.has_next", page)
        self.assertEqual(page.count("{% if "), page.count("{% endif %}"))

    def test_stylesheet_present(self):
        root = Path(__file__).resolve().parent
        self.assertTrue((root / "static/staff/fizo-hotel-frontdesk.css").is_file())

    def test_availability_is_a_distinct_real_screen(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/availability.html").read_text(encoding="utf-8")
        css = (root / "static/staff/fizo-hotel-frontdesk.css").read_text(encoding="utf-8")
        self.assertIn("fizo-availability__search", page)
        self.assertIn("fizo-availability__room", page)
        self.assertIn("available_by_type.items", page)
        self.assertIn("available_rooms|length", page)
        self.assertIn('name="check_in"', page)
        self.assertIn('name="check_out"', page)
        self.assertIn("staff-lodging-availability", page)
        self.assertNotIn("hospitality-workflow.css", page)
        self.assertIn(".fizo-availability__grid", css)
        self.assertEqual(page.count("{% if "), page.count("{% endif %}"))


    def test_reservation_creation_preserves_actual_form_and_csrf(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/reservation_form.html").read_text(encoding="utf-8")
        self.assertIn("fizo-reservation-create__form", page)
        self.assertIn("{% csrf_token %}", page)
        self.assertIn("{% for field in form %}", page)
        self.assertIn("{{ field.errors }}", page)
        self.assertIn("staff-lodging-availability", page)
        self.assertNotIn("hospitality-workflow.css", page)

    def test_reservation_detail_preserves_sensitive_actions(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/reservation_detail.html").read_text(encoding="utf-8")
        self.assertIn("fizo-reservation-detail", page)
        for action in ("set_customer", "assign_room", "check_in", "check_out",
                       "cancel", "open_folio", "folio_line"):
            with self.subTest(action=action):
                self.assertIn('value="' + action + '"', page)
        self.assertIn("can_modify_lodging", page)
        self.assertNotIn("hospitality-workflow.css", page)
        self.assertEqual(page.count("{% block "), page.count("{% endblock %}"))
