"""Retail cashier sales landing regression contract; browser acceptance separate."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse

class RetailSalesLandingTests(SimpleTestCase):
    def test_templates_parse_and_routes_resolve(self):
        get_template("staff/orders_list.html")
        get_template("staff/includes/fizo_retail_sales_landing.html")
        for route in ("staff-orders", "staff-order-quick-create", "staff-pos-shifts"):
            self.assertTrue(reverse(route).startswith("/staff/"))

    def test_checkout_requires_shift_and_preserves_existing_order_flows(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/orders_list.html").read_text(encoding="utf-8")
        landing = (root / "templates/staff/includes/fizo_retail_sales_landing.html").read_text(encoding="utf-8")
        self.assertIn("{% if show_supermarket_lane %}", page)
        self.assertIn("staff/retail-workflows.css", page)
        self.assertNotIn("fizo-retail-sales.css", page)
        self.assertIn('staff_product.business_key == "retail"', landing)
        self.assertIn('Retail{% else %}Supermarket{% endif %} / Cashier', landing)
        self.assertNotIn('Fizo / Supermarket / Cashier', landing)
        self.assertIn("supermarket_shift_open", landing)
        self.assertIn("current_outlet", landing)
        self.assertIn("staff-order-quick-create", landing)
        self.assertIn("staff/includes/orders_lanes.html", landing)
        self.assertIn('name="mode" value="hold"', landing)
        self.assertIn("staff-order-detail", landing)
        self.assertIn("returns_task", landing)
        self.assertIn("page_obj.has_next", landing)
        self.assertIn("{% csrf_token %}", landing)
        self.assertEqual(page.count("{% block "), page.count("{% endblock %}"))
        self.assertTrue((root / "static/staff/retail-workflows.css").exists())


    def test_retail_dashboard_has_independent_business_heading(self):
        root = Path(__file__).resolve().parent
        dashboard = (root / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('staff_product.business_key == "supermarket" %}Supermarket dashboard', dashboard)
        self.assertIn('staff_product.business_key == "retail" %}Retail dashboard', dashboard)
        self.assertNotIn('staff_product.business_key == "supermarket" or staff_product.business_key == "retail" %}Supermarket dashboard', dashboard)
        get_template("staff/dashboard.html")

    def test_lodging_empty_arrivals_explains_selected_property(self):
        page = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("No arrivals scheduled for today at {{ staff_dashboard_lodging_snapshot.site_name }}.", page)
        self.assertIn("{% if staff_dashboard_lodging_snapshot and staff_dashboard_lodging_snapshot.arrival_rows %}", page)
        self.assertIn("{% url 'staff-lodging-reservations' %}", page)
        get_template("staff/dashboard.html")

    def test_lodging_pulse_uses_scoped_real_property_data_and_drilldowns(self):
        page = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        for expected in ("Property pulse", "staff_dashboard_lodging_snapshot.site_name",
                         "staff_dashboard_lodging_snapshot.arrival_rows",
                         "staff_dashboard_lodging_snapshot.housekeeping_url",
                         "staff_dashboard_lodging_snapshot.maintenance_url",
                         "staff_dashboard_lodging_snapshot.open_maintenance"):
            self.assertIn(expected, page)
        get_template("staff/dashboard.html")

    def test_lodging_fallback_uses_effective_navigation_permission(self):
        dashboard = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('{% elif staff_nav.lodging %}', dashboard)
        self.assertNotIn('{% elif staff_show_lodging_nav and staff_nav.lodging %}', dashboard)
        get_template("staff/dashboard.html")

    def test_hotel_dual_role_keeps_secondary_pos_link(self):
        page = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('{% if staff_nav.orders %}<a href="{% url \'staff-orders\' %}">Open POS</a>{% endif %}', page)
        self.assertIn('href="{% url \'staff-lodging-reservations\' %}">Open reservations', page)
        get_template("staff/dashboard.html")

    def test_hotel_front_desk_precedes_optional_pos_launch(self):
        page = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        front_desk = '{% if staff_product.business_key == "lodging" and staff_nav.lodging %}'
        pos_branch = '{% elif staff_nav.orders %}'
        self.assertIn(front_desk, page)
        self.assertIn(pos_branch, page)
        self.assertLess(page.index(front_desk), page.index(pos_branch))
        self.assertIn("{% url 'staff-lodging-reservations' %}", page)
        self.assertIn("{% url 'staff-orders' %}", page)
        get_template("staff/dashboard.html")

    def test_hotel_launch_uses_guest_language(self):
        dashboard = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('staff_product.business_key == "lodging" %}Ready for the next guest?', dashboard)
        self.assertIn('staff_product.business_key == "bar" or staff_product.business_key == "lounge" %}Ready to serve the next tab?', dashboard)
        get_template("staff/dashboard.html")

    def test_dashboard_missing_membership_has_helpful_empty_state(self):
        dashboard = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("{% if memberships %}No workspace selected{% else %}No workspace available{% endif %}", dashboard)
        self.assertIn("Ask your administrator to add you to the correct business.", dashboard)
        self.assertIn('name="tenant_id" required', dashboard)
        get_template("staff/dashboard.html")

    def test_dashboard_popular_items_heading_requires_real_items(self):
        page = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("staff_dashboard_sales_snapshot and staff_dashboard_sales_snapshot.top_items %}Popular items", page)
        self.assertIn("staff_dashboard_sales_snapshot %}Sales activity", page)
        get_template("staff/dashboard.html")

    def test_dashboard_empty_panels_have_actionable_context(self):
        template = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("No ranked products to show for this period.", template)
        self.assertNotIn("No sales have been recorded in this reporting period yet.", template)
        self.assertIn("Use the quick actions to get started with your workspace.", template)
        self.assertNotIn("Nothing requiring attention is available yet.", template)
        get_template("staff/dashboard.html")

    def test_dashboard_intro_is_business_and_workspace_specific(self):
        dashboard = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Here's your store at a glance", dashboard)
        self.assertIn("Guest accounts, reservations and room readiness", dashboard)
        self.assertIn("No workspace selected", dashboard)
        self.assertIn("{% if not active_membership %}", dashboard)
        get_template("staff/dashboard.html")

    def test_dashboard_owner_navigation_remains_accessible(self):
        dashboard = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("{% if show_workspace_admin_tools %}", dashboard)
        for link in ("console-org", "console-org-setup", "staff-workspace-members", "staff-workspace-member-create"):
            self.assertIn("{% url '" + link + "' %}", dashboard)
            self.assertTrue(reverse(link).startswith("/"))
        self.assertIn("Team &amp; onboarding", dashboard)
        self.assertIn("Open admin console", dashboard)
        get_template("staff/dashboard.html")

    def test_dashboard_operational_metrics_render_in_one_section(self):
        dashboard = (Path(__file__).resolve().parent / "templates/staff/dashboard.html").read_text(encoding="utf-8")
        self.assertEqual(dashboard.count("{% for metric in staff_dashboard_operations_snapshot %}"), 1)
        self.assertIn('id="fizo-operations-pulse"', dashboard)
        self.assertIn("staff_dashboard_operations_snapshot", dashboard)
        self.assertIn("staff_dashboard_low_stock_rows", dashboard)
        self.assertIn("Full report", dashboard)
        get_template("staff/dashboard.html")

    def test_register_shift_heading_is_business_specific(self):
        root = Path(__file__).resolve().parent
        shifts = (root / "templates/staff/pos_shifts.html").read_text(encoding="utf-8")
        self.assertIn('staff_product.business_key == "supermarket"', shifts)
        self.assertIn('Supermarket{% else %}Retail{% endif %} / Cashier operations', shifts)
        self.assertIn('staff_product.workspace_label|default:"Business"', shifts)
        self.assertNotIn('Retail / Cashier operations{% else %}', shifts)
        get_template("staff/pos_shifts.html")

    def test_all_register_view_selection_uses_retail_outlet_types(self):
        root = Path(__file__).resolve().parent
        source = (root / "views_ops.py").read_text(encoding="utf-8")
        self.assertIn("visible_outlets = list(ctx[\"outlets\"])", source)
        self.assertIn("all(item.outlet_type in retail_types for item in visible_outlets)", source)
        self.assertIn('ctx["show_supermarket_lane"] = supermarket_lane', source)
        self.assertIn('ctx["show_retail_catalogue"]', source)
        self.assertIn("all(item.outlet_type in retail_types for item in outlets)", source)


    def test_primary_retail_start_sale_uses_idempotent_post(self):
        """The visible Start checkout button carries its own safe retry token."""
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/orders_list.html").read_text(encoding="utf-8")
        self.assertIn('name="quick_create_key" value="{{ quick_create_key }}"', page)
        self.assertIn("this.dataset.submitting = '1'", page)
        self.assertIn("Start checkout</button>", page)
        self.assertIn('name="quick_create_key" value="{{ quick_hold_key }}"', page)
        self.assertGreaterEqual(page.count("this.dataset.submitting = '1'"), 3)

    def test_retail_active_baskets_are_resume_cards(self):
        root = Path(__file__).resolve().parent
        lanes = (root / "templates/staff/includes/orders_lanes.html").read_text(encoding="utf-8")
        self.assertIn("{% if show_supermarket_lane %}", lanes)
        self.assertIn("fizo-active-sales", lanes)
        self.assertIn("Resume sale", lanes)
        self.assertIn("Resume &amp; collect balance", lanes)
        self.assertIn("staff-order-detail", lanes)
        self.assertIn("{% else %}", lanes)
