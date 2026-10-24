"""Source-level cashier support checks; no financial or hardware operation performed."""
from pathlib import Path
from django.template.loader import get_template
from django.test import SimpleTestCase

class FizoCashierSupportTests(SimpleTestCase):
    def test_templates_compile(self):
        for name in ("workstation_form.html", "workstation_pair.html",
                     "workstation_test.html", "order_print.html",
                     "pos/customer_display.html"):
            with self.subTest(page=name):
                get_template("staff/" + name)

    def test_pairing_and_hardware_safety_actions_remain(self):
        root = Path(__file__).resolve().parent / "templates/staff"
        pair = (root / "workstation_pair.html").read_text(encoding="utf-8")
        self.assertIn('value="revoke"', pair)
        self.assertIn('name="password"', pair)
        self.assertEqual(pair.count("<form "), pair.count("{% csrf_token %}"))
        hardware = (root / "workstation_test.html").read_text(encoding="utf-8")
        self.assertIn("hardware-print", hardware)
        self.assertIn("hardware-scan-input", hardware)
        self.assertIn("hardware-test-slip", hardware)

    def test_receipt_and_customer_display_keep_existing_values(self):
        root = Path(__file__).resolve().parent / "templates/staff"
        print_page = (root / "order_print.html").read_text(encoding="utf-8")
        for value in ("page_size", "page_margin", "body_padding",
                      "paper_width", "payment_entries", "refund_entries",
                      "order.bill_reference", "window.print()", "staff-terminal-lock"):
            self.assertIn(value, print_page)
        display = (root / "pos/customer_display.html").read_text(encoding="utf-8")
        for value in ("display_lines", "display_paid", "display_remaining",
                      "order.is_paid", 'content="4"', "order.total"):
            self.assertIn(value, display)

    def test_supermarket_has_visible_cashier_identity_and_search_shortcuts(self):
        root = Path(__file__).resolve().parent / "templates/staff"
        main = (root / "order_detail.html").read_text(encoding="utf-8")
        retail = (root / "order_detail_supermarket.html").read_text(encoding="utf-8")
        for marker in ("fizo-cashier-identity", "fizo-cashier-shortcuts",
                       "data-fizo-focus-search", "data-fizo-focus-scan",
                       "fizo-checkout-catalogue", "fizo-checkout-basket"):
            self.assertIn(marker, main)
        # Shared checkout grid/search/basket live in the parent template;
        # only the scanner-specific extension belongs to the retail block.
        for marker in ("fizo-pos-menu-search", "data-pos-menu-search", "fizo-current-basket"):
            self.assertIn(marker, main)
        self.assertIn("data-retail-scan-form", retail)
        get_template("staff/order_detail.html")
        get_template("staff/order_detail_supermarket.html")

    def test_retail_checkout_cashier_and_payment_contract(self):
        root = Path(__file__).resolve().parent
        views = (root / "views_ops.py").read_text(encoding="utf-8")
        checkout = (root / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        styles = (root / "static/staff/retail-cashier.css").read_text(encoding="utf-8")
        self.assertIn("def _can_operate_retail_checkout(", views)
        self.assertIn("MembershipRole.SERVER", views)
        self.assertIn('"record_payment"', views)
        self.assertIn('"scan_add_line"', views)
        self.assertIn('"adjust_line_qty"', views)
        self.assertIn('class="fizo-cashier-payment-summary"', checkout)
        self.assertIn('id="fizo-cashier-payment"', checkout)
        self.assertIn('data-pos-payment-form', checkout)
        self.assertIn("fizo-cashier-pay-cta", styles)
        self.assertIn("grid-template-columns:minmax(0,1fr) var(--retail-basket)", styles)
        self.assertIn("--retail-basket:minmax(390px,33.5%)", styles)
        self.assertNotIn("grid-template-columns:minmax(0,1fr)!important", styles)

    def test_legacy_grocery_script_does_not_reparent_modern_catalogue(self):
        root = Path(__file__).resolve().parent / "static/staff"
        source = (root / "grocery-checkout.js").read_text(encoding="utf-8")
        guard = 'root.querySelector(".fizo-checkout-catalogue")'
        mutation = 'right.insertBefore(basket, right.firstChild)'
        self.assertIn(guard, source)
        self.assertIn(mutation, source)
        self.assertLess(source.index(guard), source.index(mutation))
        self.assertIn('root.querySelector(".fizo-checkout-basket")', source)
