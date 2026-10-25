"""Contract tests for Fizo cashier layout and retained payment workflow."""
from pathlib import Path

from django.test import SimpleTestCase


class FizoCheckoutLayoutTests(SimpleTestCase):
    def test_catalogue_and_basket_are_separate_panes(self):
        base = Path(__file__).resolve().parent
        main = (base / "templates/staff/order_detail.html").read_text(encoding="utf-8")
        supermarket = (base / "templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        catalogue = (base / "templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        counter = (base / "static/staff/retail-counter-v2.js").read_text(encoding="utf-8")
        self.assertIn("fizo-checkout-catalogue", main)
        self.assertIn("fizo-checkout-basket", main)
        self.assertIn("line.menu_item.product_image_src", main)
        self.assertNotIn("line.menu_item.display_image_url", main)
        self.assertIn("fizo_pos_catalogue.html", main)
        self.assertIn("retail-cashier.css", supermarket)
        self.assertNotIn("fizo-checkout-v1.css", supermarket)
        self.assertTrue((base / "static/staff/retail-cashier.css").is_file())
        self.assertNotIn("grocery-checkout.css", supermarket)
        self.assertIn('name="action" value="add_line"', catalogue)
        self.assertIn('data-pos-menu-browser', catalogue)
        self.assertIn('name="action" value="record_payment"', main)
        self.assertIn("data-retail-payment-status", main)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', supermarket)
        self.assertIn("window.retailRefreshCheckout()", supermarket)
        self.assertIn("completingPayment", counter)
        self.assertIn("payment_request_key", counter)
        self.assertIn('name="action" value="adjust_line_qty"', main)
        self.assertIn('name="action" value="void_line"', main)
        self.assertIn('name="action" value="scan_add_line"', supermarket)
        self.assertIn("form.requestSubmit()", supermarket)
        self.assertIn('name="action" value="scan_add_line"', supermarket)
        self.assertIn('data-retail-scan-form', supermarket)
        self.assertIn('name="action" value="retail_line_refund"', supermarket)
        self.assertIn('if (!scanForm.checkValidity()) return;', supermarket)
        self.assertIn('name="action" value="retail_line_refund"', supermarket)
