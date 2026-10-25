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

    def test_retail_startup_hides_technical_shift_and_device_workflow(self):
        root = Path(__file__).resolve().parent
        start = (root / "templates/staff/retail_pos_start.html").read_text(encoding="utf-8")
        terminal = (root / "templates/staff/terminal.html").read_text(encoding="utf-8")
        login = (root / "templates/staff/login.html").read_text(encoding="utf-8")
        views = (root / "views_ops.py").read_text(encoding="utf-8")

        self.assertIn('name="action" value="start_selling"', start)
        self.assertIn("Cash in drawer now", start)
        self.assertIn("Start selling", start)
        self.assertIn("Which till are you using?", start)
        self.assertIn("Held sales", start)
        self.assertNotIn("Shift and drawer", start)
        self.assertNotIn("Register devices", start)
        self.assertIn("open_pos_shift(", views)
        self.assertIn("create_order_with_lines(", views)
        self.assertIn("Tenant.objects.select_for_update()", views)
        self.assertIn("Continue to checkout", terminal)
        self.assertIn("CHECKOUT TERMINAL", terminal)
        self.assertIn("STORE SIGN IN", login)

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
        self.assertIn('[data-retail-summary="subtotal"] strong', source)
        self.assertIn('[data-retail-summary="discount"] strong', source)
        self.assertIn('[data-retail-summary="tax"] strong', source)
        self.assertIn('[data-retail-summary="total"] strong', source)
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

    def test_async_refresh_never_replaces_another_sales_basket(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('var remoteBasket=remote.querySelector(".fizo-checkout-basket")', js)
        self.assertIn('basket.dataset.orderId!==remoteBasket.dataset.orderId', js)
        self.assertLess(js.index('basket.dataset.orderId!==remoteBasket.dataset.orderId'),
                        js.index('current.replaceChildren.apply(current'))

    def test_first_item_pay_shortcut_shows_current_due(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('label.textContent="Pay "+dueLabel.textContent.trim()', js)
        self.assertIn('var label=payLink.querySelector("span")', js)
        self.assertIn('if(payLink&&payLink.dataset.retailPayBound!=="1")', js)

    def test_first_item_adds_authorized_pay_shortcut_before_binding(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('remoteBasket.querySelector(".fizo-cashier-pay-cta")', js)
        self.assertIn('liveSummary.appendChild(document.importNode(remoteCta,true))', js)
        self.assertLess(js.index('liveSummary.appendChild(document.importNode(remoteCta,true))'),
                        js.index('document.dispatchEvent(new Event("retail:payment-controls-added"))'))
        self.assertIn("function bindRetailPayShortcuts()", js)

    def test_first_item_checks_real_balance_before_binding_payment(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('var serverDue=nextCash.getAttribute("data-balance-due")', js)
        self.assertIn('!Number.isFinite(Number(serverDue))', js)
        self.assertIn('var oldDue=activatingPayment ? null : cash.getAttribute("data-balance-due")', js)
        self.assertLess(js.index('current.replaceChildren.apply(current'),
                        js.index('document.dispatchEvent(new Event("retail:payment-controls-added"))'))

    def test_first_item_activates_server_rendered_payment_controls_inline(self):
        root = Path(__file__).resolve().parent
        js = (root / "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        template = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn("var activatingPayment=!activePayment&&!!remotePayment", js)
        self.assertIn('var freshCard=remotePayment.closest(".staff-card--pos")', js)
        self.assertIn("document.importNode(freshCard,true)", js)
        self.assertIn('new Event("retail:payment-controls-added")', js)
        self.assertIn('function bindRetailPayShortcuts()', js)
        self.assertIn('function bindRetailPaymentControls()', template)
        self.assertIn('document.addEventListener("retail:payment-controls-added", bindRetailPaymentControls)', template)
        self.assertNotIn('var asyncReady=!!(window.fetch&&window.FormData&&paymentForm&&', js)
        self.assertIn('document.querySelector("#fizo-current-basket .fizo-retail-basket-items") &&', template)

    def test_inline_refresh_rejects_incomplete_totals_before_mutating_basket(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('var amountSelectors=[', js)
        self.assertIn('if(amountSelectors.some(function(selector)', js)
        self.assertIn('Incomplete checkout totals; reopen this sale to continue.', js)
        self.assertLess(js.index('if(amountSelectors.some(function(selector)'),
                        js.index('current.replaceChildren.apply(current'))

    def test_inline_basket_refresh_checks_payment_transition_before_dom_changes(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        # Empty baskets can acquire payment controls on the first item.
        # Existing payment controls may disappear only after the authoritative
        # page confirms the sale is complete. Any other disappearance, or an
        # unexpected cash-calculator transition, must block DOM replacement.
        self.assertIn("var activatingPayment=!activePayment&&!!remotePayment", js)
        self.assertIn("var completingPayment=!!activePayment&&!remotePayment&&", js)
        self.assertIn('remoteBasket.classList.contains("is-complete")', js)
        self.assertIn("if(activePayment&&!remotePayment&&!completingPayment)", js)
        self.assertIn("if(!!cash!==!!nextCash && !activatingPayment && !completingPayment)", js)
        self.assertIn('var serverDue=nextCash.getAttribute("data-balance-due")', js)
        self.assertLess(js.index("if(activePayment&&!remotePayment&&!completingPayment)"),
                        js.index("current.replaceChildren.apply(current"))
        self.assertLess(js.index("if(!!cash!==!!nextCash && !activatingPayment && !completingPayment)"),
                        js.index("current.replaceChildren.apply(current"))

    def test_inline_refresh_preserves_manual_partial_tender(self):
        js = (Path(__file__).resolve().parent /
              "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn('var tender=cash.querySelector("[data-retail-cash-received]")', js)
        self.assertIn('(!tender||!tender.value.trim())', js)
        self.assertIn('Number(amount.value)===Number(oldDue)', js)
        self.assertIn("if(activePayment&&remotePayment&&!completingPayment)", js)
        self.assertIn("if(activePayment&&!remotePayment&&!completingPayment)", js)

    def test_held_basket_lock_is_inside_database_transaction(self):
        services = (Path(__file__).resolve().parent.parent /
                    "pos/services/orders.py").read_text(encoding="utf-8")
        self.assertIn(
            "@transaction.atomic\ndef hold_open_order(*, order: Order, hold_label: str, user)",
            services,
        )
        self.assertNotIn(
            "@transaction.atomic\n@transaction.atomic\ndef hold_open_order",
            services,
        )
        self.assertIn("Order.objects.select_for_update().get(pk=order.pk)", services)

    def test_payment_and_refund_balances_are_tenant_scoped(self):
        payments = (Path(__file__).resolve().parent.parent /
                    "pos/services/payments.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            payments.count('Payment.objects.filter(order_id=locked.id, tenant_id=locked.tenant_id)'),
            1,
        )
        self.assertGreaterEqual(
            payments.count('Refund.objects.filter(order_id=locked.id, tenant_id=locked.tenant_id)'),
            1,
        )
        self.assertIn(
            'Refund.objects.filter(payment_id=p.id, tenant_id=order.tenant_id)',
            payments,
        )

    def test_open_basket_cancellation_does_not_restock_unsold_inventory(self):
        root = Path(__file__).resolve().parent
        orders = (root.parent / "pos/services/orders.py").read_text(encoding="utf-8")
        payments = (root.parent / "pos/services/payments.py").read_text(encoding="utf-8")
        cancel = orders.split("def cancel_open_unpaid_order", 1)[1].split(
            "def process_supermarket_line_return", 1
        )[0]
        self.assertNotIn("apply_manual_stock_change", cancel)
        self.assertNotIn("StockReason.ADJUST_IN", cancel)
        self.assertIn("validate_and_consume_stock_for_paid_order(locked, user)", payments)

    def test_part_paid_cancellation_requires_exact_refund_reconciliation(self):
        root = Path(__file__).resolve().parent
        services = (root.parent / "pos/services/orders.py").read_text(encoding="utf-8")
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        detail = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        self.assertIn('remaining_refund = (recorded - refunded).quantize(Decimal("0.01"))', services)
        self.assertIn('code="refund_required"', services)
        self.assertIn('Payment.objects.filter(order_id=locked.id, tenant_id=locked.tenant_id)', services)
        self.assertIn('Refund.objects.filter(order_id=locked.id, tenant_id=locked.tenant_id)', services)
        self.assertIn('"recorded_payments": str(recorded)', services)
        self.assertIn('"recorded_refunds": str(refunded)', services)
        self.assertIn('"net_payment": str((recorded - refunded).quantize(Decimal("0.01")))', services)
        self.assertIn('Use the authorized refund controls below, then cancel this basket again.', view)
        self.assertIn('href="#retail-refund-controls">Refund {{ order.currency }} {{ refundable_remaining }} before void</a>', detail)
        self.assertIn('Supervisor refund {{ order.currency }} {{ refundable_remaining }} required', detail)

    def test_refund_required_messages_never_render_raw_drf_containers(self):
        view = (Path(__file__).resolve().parent / "views_ops.py").read_text(encoding="utf-8")
        void_block = view.split("    def _post_void_order(", 1)[1].split(
            "    def _post_apply_promotion(", 1
        )[0]
        self.assertIn("def _drf_detail_messages", view)
        self.assertIn("def _drf_has_code", view)
        self.assertIn('_drf_has_code(exc.get_codes(), "refund_required")', void_block)
        self.assertIn("_drf_detail_messages(exc.detail)", void_block)
        self.assertNotIn("messages.error(request, str(exc.detail))", void_block)
        self.assertNotIn("ErrorDetail(", void_block)

    def test_refunds_use_rendered_stable_idempotency_keys(self):
        root = Path(__file__).resolve().parent
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        detail = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        supermarket = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn('ctx["refund_request_key"] = uuid.uuid4()', view)
        self.assertIn('ctx["retail_refund_request_key"] = uuid.uuid4()', view)
        self.assertIn('request_key = self._refund_request_key(request)', view)
        self.assertIn('request_key = self._refund_request_key(request, "retail_refund_request_key")', view)
        self.assertGreaterEqual(view.count('idempotency_key=request_key'), 2)
        self.assertGreaterEqual(view.count('request_key=request_key'), 2)
        self.assertIn('name="refund_request_key" value="{{ refund_request_key }}"', detail)
        self.assertIn('name="retail_refund_request_key" value="{{ retail_refund_request_key }}"', supermarket)

    def test_part_paid_quantity_reduction_routes_to_authorized_refund_controls(self):
        root = Path(__file__).resolve().parent
        services = (root.parent / "pos/services/orders.py").read_text(encoding="utf-8")
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        detail = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        checkout = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn('code="refund_required"', services)
        self.assertIn('Refund {locked_o.currency} {excess:.2f} before applying this reduction.', services)
        self.assertIn('"refund_required": refund_required', view)
        self.assertIn('data-retail-refund-form', detail)
        self.assertIn('if (data.refund_required)', checkout)
        self.assertIn('"Open refund controls"', checkout)

    def test_barcode_and_product_errors_share_read_only_recovery(self):
        root = Path(__file__).resolve().parent
        js = (root / "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        scan = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn("window.retailShowCheckoutRecovery=showCheckoutRecovery", js)
        self.assertIn("showCheckoutRecovery(live,error)", js)
        self.assertIn("window.retailShowCheckoutRecovery(scanStatus, error)", scan)
        self.assertIn("retry.type=\"button\"", js)
        self.assertIn("window.location.reload()", js)

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

    def test_failed_product_confirmation_offers_read_only_recovery(self):
        script = (Path(__file__).resolve().parent /
                  "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn("function showCheckoutRecovery(node,error)", script)
        self.assertIn('retry.type="button"', script)
        self.assertIn('window.location.reload()', script)
        self.assertIn("showCheckoutRecovery(live,error);", script)

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

    def test_staff_help_is_real_and_cashier_footer_exposes_it(self):
        root = Path(__file__).resolve().parent
        urls = (root / "urls.py").read_text(encoding="utf-8")
        views = (root / "views.py").read_text(encoding="utf-8")
        sidebar = (root / "templates/staff/includes/sidebar.html").read_text(encoding="utf-8")
        help_page = (root / "templates/staff/help.html").read_text(encoding="utf-8")
        css = (root / "static/staff/retail-cashier.css").read_text(encoding="utf-8")
        self.assertIn('path("help/", views.StaffHelpView.as_view(), name="staff-help")', urls)
        self.assertIn("class StaffHelpView(LoginRequiredMixin, TemplateView):", views)
        self.assertIn("fz-sidefoot__help", sidebar)
        self.assertIn("{% url 'staff-help' %}", sidebar)
        self.assertIn("Cashier quick guide", help_page)
        self.assertIn("F3", help_page)
        self.assertIn(".fz-sidefoot__pin{display:none}", css)
        self.assertIn(".fz-sidefoot__help,", css)

    def test_live_cashier_sidebar_matches_approved_operational_rail(self):
        root = Path(__file__).resolve().parent
        sidebar = (root / "templates/staff/includes/sidebar.html").read_text(encoding="utf-8")
        css = (root / "static/staff/retail-cashier.css").read_text(encoding="utf-8")
        self.assertIn('class="fz-nav__dashboard"', sidebar)
        self.assertIn('class="fz-nav__deliveries"', sidebar)
        self.assertIn("}Reports{% else %}Sales &amp; reports{% endif %}", sidebar)
        self.assertIn(".fz-nav__dashboard,", css)
        self.assertIn(".fz-nav__deliveries{display:none}", css)

    def test_dynamic_payment_and_cash_controls_bind_independently(self):
        checkout = (Path(__file__).resolve().parent /
                    "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn(
            'paymentForm && paymentForm.dataset.retailPaymentBound !== "1"',
            checkout,
        )
        self.assertIn('paymentForm.dataset.retailPaymentBound = "1"', checkout)
        self.assertNotIn(
            'if(paymentForm && paymentForm.dataset.retailPaymentBound==="1") return;',
            checkout,
        )
        self.assertIn(
            'cashPanel && cashPanel.dataset.retailCashBound !== "1"',
            checkout,
        )
        self.assertIn('cashPanel.dataset.retailCashBound = "1"', checkout)
        self.assertIn(
            'meta.textContent = "Sub " + values.subtotal + " · Disc " + values.discount + " · Tax " + values.tax',
            checkout,
        )
        self.assertNotIn("values.discount);\\n    show(", checkout)

    def test_approved_product_card_density_and_named_totals(self):
        root = Path(__file__).resolve().parent
        css = (root / "static/staff/retail-cashier.css").read_text(encoding="utf-8")
        detail = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        checkout = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        view = (root / "views_ops.py").read_text(encoding="utf-8")
        self.assertIn("min-height:184px", css)
        self.assertIn("height:106px", css)
        self.assertIn('data-retail-summary="subtotal"', detail)
        self.assertIn('data-retail-summary="discount"', detail)
        self.assertIn('data-retail-summary="tax"', detail)
        self.assertIn('data-retail-summary="total"', detail)
        self.assertIn('"discount": str(order.discount_amount)', view)
        self.assertIn("values.discount", checkout)
        self.assertNotIn(".fizo-retail-basket-summary > div:nth-child(1) strong", checkout)
        self.assertNotIn(".fizo-retail-basket-summary > div:nth-child(2) strong", checkout)

    def test_cashier_payment_stack_matches_compact_target(self):
        root = Path(__file__).resolve().parent
        detail = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        css = (root / "static/staff/retail-cashier.css").read_text(encoding="utf-8")
        js = (root / "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn(
            '<span>Pay {{ order.currency }} {{ balance_due }}</span>',
            detail,
        )
        self.assertNotIn(
            'aria-hidden="true"></i> Take payment <i class="bi bi-arrow-right"',
            detail,
        )
        self.assertIn('class="reference-partial-payment"', detail)
        self.assertNotIn("Continue this basket's payment", detail)
        self.assertIn(".reference-partial-payment{", css)
        self.assertIn('label.textContent="Pay "+dueLabel.textContent.trim()', js)
        self.assertNotIn("Confirm quantity and add to basket.", js)
        self.assertNotIn("Confirm quantity and choose Add to basket.", js)

    def test_completed_retail_sale_keeps_cashier_in_checkout_for_next_customer(self):
        root = Path(__file__).resolve().parent
        detail = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        supermarket = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        css = (root / "static/staff/retail-cashier.css").read_text(encoding="utf-8")

        self.assertIn("fizo-sale-complete-actions", detail)
        self.assertIn("Sale complete", detail)
        self.assertIn("Receipt ready", detail)
        self.assertIn("Print receipt", detail)
        self.assertIn("Next customer", detail)
        self.assertIn("fizo-sale-next-customer", detail)
        self.assertIn('action="{% url \'staff-order-quick-create\' %}"', detail)
        self.assertIn('{% if not order.is_paid %}\n        <nav class="fizo-retail-basket-tools"', detail)
        complete_block = detail.split('<section class="fizo-sale-complete-actions"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(complete_block.count("Print receipt"), 1)
        self.assertIn('name="quick_create_key" value="{{ next_sale_request_key }}"', detail)
        self.assertIn("is-complete", detail)
        self.assertIn(".fizo-checkout-basket.is-complete .fizo-cashier-payment-summary{display:none}", css)
        self.assertIn(".fizo-sale-complete-actions{", css)
        self.assertIn(".fizo-sale-next-customer .staff-btn{width:100%;font-size:15px}", css)

        # Do not hide the daily next-customer flow in the auxiliary tools card.
        self.assertNotIn("reference-sale-complete", supermarket)
        self.assertNotIn(".reference-sale-complete{", css)
        # Retail completion must not force a lock; hospitality keeps its lock action.
        self.assertIn("{% if order.status == 'closed' and not is_supermarket_outlet %}", detail)
        self.assertIn("Done · lock terminal", detail)

    def test_basket_stays_tall_until_cashier_opens_payment(self):
        root = Path(__file__).resolve().parent
        supermarket = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        detail = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        css = (root / "static/staff/retail-cashier.css").read_text(encoding="utf-8")
        js = (root / "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")

        self.assertNotIn("If the customer gives less than the amount due", supermarket)
        self.assertNotIn("The cash-received figure is not the sale amount", supermarket)
        self.assertIn("Partial cash. Save this amount, then collect or hold the balance.", supermarket)
        self.assertIn("Change ready.", supermarket)
        self.assertIn("{% if is_supermarket_outlet %}Pay{% else %}Record payment{% endif %}", detail)
        self.assertNotIn("Choose a method, confirm the amount, then record the payment.", detail)

        self.assertIn("min-height:180px", css)
        self.assertIn("grid-template-columns:48px minmax(0,1fr) auto", css)
        self.assertIn(".fizo-checkout-basket>.reference-payment-card{", css)
        self.assertIn("display:none;position:absolute", css)
        self.assertIn(".fizo-checkout-basket>.reference-payment-card.is-open{display:block}", css)
        self.assertIn(".fizo-checkout-basket>.reference-payment-idle{display:none!important}", css)

        self.assertIn("function openPaymentDrawer()", js)
        self.assertIn('paymentCard.classList.add("is-open")', js)
        self.assertIn("function closePaymentDrawer()", js)
        self.assertIn("newCard.appendChild(newCash)", js)
        self.assertIn("setupPaymentDrawer(newCard,newCash)", js)
        self.assertNotIn('card.scrollIntoView({behavior:"smooth",block:"nearest"})', js)

    def test_approved_cashier_header_order_and_compact_density(self):
        root = Path(__file__).resolve().parent
        detail = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        supermarket = (root / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        css = (root / "static/staff/retail-cashier.css").read_text(encoding="utf-8")
        register = detail.index('class="fizo-cashier-identity__register"')
        cashier = detail.index('class="fizo-cashier-identity__person"')
        customer_display = detail.index('class="reference-customer-display-link"')
        self.assertLess(register, cashier)
        self.assertLess(cashier, customer_display)
        self.assertIn("--retail-sidebar:104px", css)
        self.assertIn("min-height:68px;margin:0 -14px 8px", css)
        self.assertIn("grid-template-columns:repeat(5,minmax(0,1fr))", css)
        self.assertIn("flex:0 0 96px;min-width:96px;min-height:72px", css)
        self.assertIn("grid-template-columns:48px minmax(0,1fr) auto", css)
        self.assertIn("background:#e7f8ed;color:#007940;font-weight:800", css)
        self.assertIn("background:#e7f8ed;color:#087a43;font-weight:850", css)
        self.assertIn("retail-cashier.css' %}?v=20261025.8", supermarket)
        self.assertIn("retail-counter-v2.js' %}?v=20261025.4", detail)

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
