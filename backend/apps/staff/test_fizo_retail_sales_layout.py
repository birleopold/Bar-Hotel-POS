"""Retail cashier sales landing regression contract; browser acceptance separate."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse

class RetailSalesLandingTests(SimpleTestCase):
    def test_staff_terminal_lock_is_scoped_by_tenant_and_account(self):
        root = Path(__file__).resolve().parent
        base = (root / "templates/staff/base.html").read_text(encoding="utf-8")
        self.assertIn("staff-terminal-lock:{{ request.tenant.pk", base)
        self.assertIn("{{ request.user.pk|escapejs }}", base)
        self.assertIn("event.key === lockKey", base)
        self.assertNotIn("event.key === 'staff-terminal-lock'", base)

    def test_retail_header_goes_to_register_and_shows_signed_in_operator(self):
        root = Path(__file__).resolve().parent
        header = (root / "templates/staff/includes/nav.html").read_text(encoding="utf-8")
        sidebar = (root / "templates/staff/includes/sidebar.html").read_text(encoding="utf-8")
        foundation = (root / "static/staff/fizo-fresh.css").read_text(encoding="utf-8")
        self.assertIn("{% url 'staff-retail-pos-entry' %}", header)
        self.assertIn("staff_product.business_key == 'supermarket'", header)
        self.assertIn("request.user.get_full_name|default:request.user.email", header)
        self.assertIn("fz-top-operator", foundation)
        self.assertIn("{% url 'staff-retail-pos-entry' %}", sidebar)

    def test_receipt_uses_shared_pin_idle_policy_and_scoped_lock_broadcast(self):
        root = Path(__file__).resolve().parent
        receipt = (root / "templates/staff/order_print.html").read_text(encoding="utf-8")
        shell = (root / "templates/staff/base.html").read_text(encoding="utf-8")
        self.assertIn("{{ staff_pin_idle_ms|default:120000 }}", receipt)
        self.assertIn("{{ staff_pin_idle_ms|default:120000 }}", shell)
        self.assertIn('staff-terminal-lock:{{ request.tenant.pk', receipt)
        self.assertIn("{{ request.user.pk|escapejs }}", receipt)
        self.assertIn("event.key === lockKey", receipt)
        self.assertNotIn("setTimeout(lock, 115000)", receipt)
        self.assertNotIn("event.key === 'staff-terminal-lock'", receipt)

    def test_receipt_labels_currency_and_net_paid_unambiguously(self):
        template = (Path(__file__).resolve().parent /
                    "templates/staff/order_print.html").read_text(encoding="utf-8")
        self.assertIn("Tax {{ order.currency }} {{ order.tax_total }}", template)
        self.assertIn("Net paid {{ order.currency }} {{ amount_paid }}", template)
        self.assertIn("Balance {{ order.currency }} {{ balance_due|floatformat:2 }}", template)
        self.assertIn("{{ order.currency }} {{ r.amount }}", template)

    def test_retail_quantity_updates_every_visible_total_and_change_calculator(self):
        source = (Path(__file__).resolve().parent /
                  "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        # Regression: only updating the old page header left the approved
        # right-side basket, Pay CTA, tender and change calculator stale.
        self.assertIn('function updateBasketAmounts(values)', source)
        self.assertIn('updateBasketAmounts(data);', source)
        self.assertIn('.fizo-retail-basket-summary__total strong', source)
        self.assertIn('.fizo-retail-basket-summary > div:nth-child(1) strong', source)
        self.assertIn('.fizo-retail-basket-summary > div:nth-child(2) strong', source)
        self.assertIn('.fizo-cashier-pay-cta span', source)
        self.assertIn('new Event("retail:balance-updated")', source)
        self.assertIn('cashPanel.addEventListener("retail:balance-updated"', source)
        self.assertIn('Number(payment.value) === Number(oldDue)', source)
        self.assertIn('(!enteredCash || !enteredCash.value.trim())', source)
        self.assertIn('Number(localPayment.value) === Number(previousDue)', source)
        self.assertIn('remotePayment.value', source)
        self.assertIn('reconcileFromServer()', source)

    def test_retail_quantity_outlet_denial_returns_forbidden_json(self):
        source = (Path(__file__).resolve().parent /
                  "views_ops.py").read_text(encoding="utf-8")
        # The browser stepper expects a structured denial, not a login or
        # order-page redirect which can leave the displayed basket stale.
        gate = source.split(
            'if not staff_outlet_allowed_for_membership(m, order.outlet_id):'
        )[1].split('if action == "ack_ready_line":', 1)[0]
        self.assertIn('action == "adjust_line_qty"', gate)
        self.assertIn('request.headers.get("X-Requested-With") == "XMLHttpRequest"', gate)
        self.assertIn('return JsonResponse({"ok": False, "message": message}, status=403)', gate)

    def test_inline_basket_refresh_checks_remote_payment_before_dom_changes(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('if(!!cash!==!!nextCash)', js)
        self.assertIn('!nextCash.hasAttribute("data-balance-due")', js)
        self.assertLess(js.index('if(!!cash!==!!nextCash)'),
                        js.index('current.replaceChildren.apply(current'))
        self.assertLess(js.index('if(!!activePayment!==!!remotePayment)'),
                        js.index('current.replaceChildren.apply(current'))

    def test_inline_refresh_preserves_manual_partial_tender(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('var tender=cash.querySelector("[data-retail-cash-received]")', js)
        self.assertIn('(!tender||!tender.value.trim())', js)
        self.assertIn('Number(amount.value)===Number(oldDue)', js)
        self.assertIn('if(!!activePayment!==!!remotePayment)', js)
        self.assertLess(js.index('if(!!activePayment!==!!remotePayment)'),
                        js.index('current.replaceChildren.apply(current'))

    def test_barcode_scan_json_and_shared_inline_basket_refresh(self):
        root = Path(__file__).resolve().parent
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        scan = view.split("    def _post_scan_add_line(", 1)[1].split(
            "    def _post_line_discount(", 1)[0]
        template = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        js = (root / "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('"ok": True', scan)
        self.assertIn('"ok": False', scan)
        self.assertIn("window.retailRefreshCheckout()", template)
        self.assertIn("if (!response.ok || !data.ok)", template)
        self.assertIn("window.retailRefreshCheckout=refreshCheckout", js)
        self.assertIn('new Event("retail:basket-lines-replaced")', js)

    def test_retail_product_add_requires_explicit_server_confirmation(self):
        root = Path(__file__).resolve().parent
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        js = (root / "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        handler = view.split("    def _post_add_line(", 1)[1].split(
            "    def _post_add_service_line(", 1)[0]
        self.assertIn('"X-Requested-With") == "XMLHttpRequest"', handler)
        self.assertIn('"ok": True', handler)
        self.assertIn('"ok": False', handler)
        self.assertIn('if(response.redirected)', js)
        self.assertIn('if(!response.ok||!data.ok)', js)
        self.assertIn('return fetch(window.location.href', js)

    def test_retail_quantity_confirmation_has_no_false_success_fallback(self):
        root = Path(__file__).resolve().parent
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        template = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertNotIn('"refresh_required": True', view)
        self.assertNotIn("data.refresh_required", template)

    def test_retail_stepper_reports_redirects_and_http_failures(self):
        source = (Path(__file__).resolve().parent /
                  "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn('redirect: "follow"', source)
        self.assertIn("response.redirected", source)
        self.assertIn('response.headers.get("Content-Type")', source)
        self.assertIn("Quantity unchanged.", source)

    def test_retail_stepper_uses_real_form_action_not_shadowed_input(self):
        source = (Path(__file__).resolve().parent /
                  "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        # The checkout form includes <input name="action">, which makes
        # form.action resolve to an HTMLInputElement rather than a URL.
        self.assertIn('name="action" value="adjust_line_qty"', (
            Path(__file__).resolve().parent /
            "templates/staff/order_detail.html").read_text(encoding="utf-8"))
        self.assertIn('form.getAttribute("action") || window.location.pathname', source)
        self.assertNotIn("fetch(form.action ||", source)

    def test_customer_screen_uses_persistent_session_not_worker_local_cache(self):
        source = (Path(__file__).resolve().parent /
                  "views_customer_display.py").read_text(encoding="utf-8")
        self.assertIn("request.session[customer_display_active_key(", source)
        self.assertIn("request.session.get(customer_display_active_key(", source)
        self.assertIn("request.session.pop(key, None)", source)
        self.assertNotIn("cache.get(", source)
        self.assertNotIn("cache.set(", source)

    def test_holding_sale_discards_only_transient_customer_cash_preview(self):
        root = Path(__file__).resolve().parent
        js = (root / "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        template = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        self.assertIn('data-order-id="{{ order.id }}"', template)
        self.assertIn('var holdForm=holdAction&&holdAction.form;', js)
        self.assertIn('localStorage.removeItem("pos:tender:"+basket.dataset.orderId)', js)
        self.assertIn('holdForm.addEventListener("submit"', js)

    def test_customer_display_hides_stale_tender_and_blank_on_repeated_session_loss(self):
        root = Path(__file__).resolve().parent
        script = (root / "static/staff/customer-display-live.js").read_text(encoding="utf-8")
        template = (root / "templates/staff/pos/customer_display.html").read_text(encoding="utf-8")
        view = (root / "views_customer_display.py").read_text(encoding="utf-8")
        self.assertIn('data-current-due="{{ display_remaining }}"', template)
        self.assertIn('Math.abs(record.due - liveDue) > 0.005', script)
        self.assertIn('root.setAttribute("data-current-due"', script)
        self.assertIn('authorizationFailures >= 3', script)
        self.assertIn('root.replaceChildren()', script)
        self.assertIn('root.setAttribute("data-active-order", "")', script)
        self.assertIn('table_label=""', view)
        self.assertIn('not order.table_label', view)

    def test_customer_display_ignores_single_idle_poll_and_pin_redirect(self):
        script = (Path(__file__).resolve().parent /
                  "static/staff/customer-display-live.js").read_text(encoding="utf-8")
        self.assertIn("pendingIdle < 3", script)
        self.assertIn("lastOrderId = nextOrderId", script)
        self.assertIn("if (response.redirected) throw", script)
        self.assertNotIn("window.location.replace(next.href)", script)

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


    def test_sale_buttons_recover_when_browser_restores_orders_page(self):
        page = (Path(__file__).resolve().parent /
                "templates/staff/orders_list.html").read_text(encoding="utf-8")
        self.assertIn("window.addEventListener('pageshow'", page)
        self.assertIn("delete form.dataset.submitting", page)
        self.assertIn('button.disabled = false', page)
        self.assertIn("staff-order-quick-create", page)

    def test_primary_retail_start_sale_uses_idempotent_post(self):
        """The visible Start checkout button carries its own safe retry token."""
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/orders_list.html").read_text(encoding="utf-8")
        self.assertIn('name="quick_create_key" value="{{ quick_create_key }}"', page)
        self.assertIn("this.dataset.submitting = '1'", page)
        self.assertIn("Start checkout</button>", page)
        self.assertIn('name="quick_create_key" value="{{ quick_hold_key }}"', page)
        self.assertGreaterEqual(page.count("this.dataset.submitting = '1'"), 3)

    def test_sales_history_labels_actual_outlet_and_supported_search(self):
        landing = (Path(__file__).resolve().parent /
                   "templates/staff/includes/fizo_retail_sales_landing.html").read_text(encoding="utf-8")
        self.assertIn("<th>Outlet</th>", landing)
        self.assertIn("{{ o.outlet.name }}", landing)
        self.assertIn("Receipt / outlet / held-basket note", landing)
        self.assertNotIn("<th>Register</th>", landing)

    def test_owner_store_shortcuts_remain_outside_dismissible_setup(self):
        dashboard = (Path(__file__).resolve().parent /
                     "templates/staff/dashboard.html").read_text(encoding="utf-8")
        management = dashboard.split("{% if show_workspace_admin_tools %}", 1)[1].split(
            "{% if show_workspace_setup_cta %}", 1)[0]
        self.assertIn("Configure payments and tills", management)
        self.assertIn("Register cash", management)
        self.assertIn("console-org-menu-item-create", management)

    def test_retail_landing_exposes_live_shift_state(self):
        landing = (Path(__file__).resolve().parent /
                   "templates/staff/includes/fizo_retail_sales_landing.html").read_text(encoding="utf-8")
        self.assertIn("orders-supermarket-lane-card", landing)
        self.assertIn('data-shift-status="{% if supermarket_shift_open %}open{% else %}closed{% endif %}"', landing)
        self.assertIn("Supermarket lane", landing)
        self.assertIn("Retail lane", landing)

    def test_retail_sales_history_labels_paid_and_due_with_order_currency(self):
        landing = (Path(__file__).resolve().parent /
                   "templates/staff/includes/fizo_retail_sales_landing.html").read_text(encoding="utf-8")
        self.assertIn("Paid {{ o.currency }} {{ o.display_paid }}", landing)
        self.assertIn("Due {{ o.currency }} {{ o.display_balance }}", landing)

    def test_retail_active_baskets_are_resume_cards(self):
        root = Path(__file__).resolve().parent
        lanes = (root / "templates/staff/includes/orders_lanes.html").read_text(encoding="utf-8")
        self.assertIn("{% if show_supermarket_lane %}", lanes)
        self.assertIn("fizo-active-sales", lanes)
        self.assertIn("Resume sale", lanes)
        self.assertIn("Resume basket", lanes)
        self.assertIn('name="action" value="resume_order"', lanes)
        self.assertIn("staff-order-detail", lanes)
        self.assertIn("{% else %}", lanes)
