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
