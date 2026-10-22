"""Source-level contract for hotel reservation register (not browser acceptance)."""
from pathlib import Path

from django.test import SimpleTestCase
from django.template.loader import get_template


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


    def test_rooms_directory_retains_real_search_and_data(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/rooms_list.html").read_text(encoding="utf-8")
        self.assertIn("fizo-room-directory__grid", page)
        self.assertIn('name="q"', page)
        self.assertIn("room_search_q", page)
        self.assertIn("r.get_status_display", page)
        self.assertIn("r.room_type.name", page)
        self.assertNotIn("hospitality-workflow.css", page)

    def test_room_types_show_real_rate_windows(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/room_types_list.html").read_text(encoding="utf-8")
        self.assertIn("fizo-room-types__grid", page)
        self.assertIn("rt.max_occupancy", page)
        self.assertIn("rt.rate_windows.all", page)
        self.assertIn("w.nightly_amount", page)
        self.assertNotIn("hospitality-workflow.css", page)


    def test_housekeeping_retains_all_real_room_actions(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/housekeeping.html").read_text(encoding="utf-8")
        self.assertIn('class="fizo-hotel fizo-housekeeping"', page)
        self.assertNotIn("hospitality-workflow.css", page)
        for action in ("claim", "start", "finish", "inspect", "reopen"):
            with self.subTest(action=action):
                self.assertIn('value="' + action + '"', page)
        self.assertIn("can_modify_lodging", page)
        self.assertEqual(page.count("<form "), page.count("{% csrf_token %}"))

    def test_maintenance_keeps_work_order_and_status_forms(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/maintenance.html").read_text(encoding="utf-8")
        self.assertIn('class="fizo-hotel fizo-maintenance"', page)
        self.assertNotIn("hospitality-workflow.css", page)
        for action in ("status", "create"):
            self.assertIn('value="' + action + '"', page)
        self.assertIn("can_manage_housekeeping_workflows", page)
        self.assertEqual(page.count("<form "), page.count("{% csrf_token %}"))


    def test_remaining_hotel_screens_retire_legacy_theme_and_keep_actions(self):
        root = Path(__file__).resolve().parent
        lodging = root / "templates/staff/lodging"
        for name in ("folios_list.html", "folio_detail.html", "tape_chart.html", "night_audit.html"):
            with self.subTest(page=name):
                page = (lodging / name).read_text(encoding="utf-8")
                self.assertIn("fizo-hotel-frontdesk.css", page)
                self.assertIn('class="fizo-hotel ', page)
                self.assertNotIn("hospitality-workflow.css", page)
                self.assertEqual(page.count("{% block "), page.count("{% endblock %}"))
        folio = (lodging / "folio_detail.html").read_text(encoding="utf-8")
        self.assertIn("Record payment", folio)
        self.assertIn("payment_form.amount", folio)
        self.assertIn("membership_can_manage_folios", folio)
        self.assertIn("{% csrf_token %}", folio)
        audit = (lodging / "night_audit.html").read_text(encoding="utf-8")
        self.assertIn('value="post_room_night"', audit)
        self.assertIn('value="close_audit"', audit)
        self.assertIn("snapshot.blockers", audit)
        self.assertEqual(audit.count('<form '), 3)
        self.assertEqual(audit.count('{% csrf_token %}'), 2)
        tape = (lodging / "tape_chart.html").read_text(encoding="utf-8")
        self.assertIn("tape_dates", tape)
        self.assertIn("tape_rows", tape)
        self.assertIn("staff-lodging-reservation-detail", tape)

    def test_hotel_subnav_respects_existing_access_gates(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/lodging/includes/subnav.html").read_text(encoding="utf-8")
        self.assertIn('class="fizo-hotel-tabs"', page)
        for gate in ("membership_can_manage_reservations", "membership_can_manage_folios",
                     "membership_can_manage_room_inventory", "membership_can_access_housekeeping",
                     "membership_can_manage_housekeeping_workflows"):
            self.assertIn(gate, page)
        self.assertNotIn("staff-subnav-pills", page)

    def test_all_thirteen_hotel_templates_compile(self):
        """Django parses each page, include and inherited block at test time."""
        names = (
            "availability.html", "folio_detail.html", "folios_list.html",
            "housekeeping.html", "includes/subnav.html", "maintenance.html",
            "night_audit.html", "reservation_detail.html", "reservation_form.html",
            "reservations_list.html", "room_types_list.html", "rooms_list.html",
            "tape_chart.html",
        )
        for name in names:
            with self.subTest(template=name):
                get_template("staff/lodging/" + name)
