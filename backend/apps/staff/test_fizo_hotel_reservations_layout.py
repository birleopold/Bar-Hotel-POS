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
