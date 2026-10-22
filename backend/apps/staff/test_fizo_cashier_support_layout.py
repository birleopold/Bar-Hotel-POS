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
        for marker in ("fizo-pos-menu-search", "data-pos-menu-search",
                       "data-retail-scan-form", "fizo-current-basket"):
            self.assertIn(marker, retail)
        get_template("staff/order_detail.html")
        get_template("staff/order_detail_supermarket.html")
