"""Approved grocery cashier layout source contracts; no live transaction performed."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template

class FizoRetailCheckoutApprovedTests(SimpleTestCase):
    def test_checkout_templates_compile(self):
        for name in ("staff/order_detail_supermarket.html","staff/order_detail.html","staff/includes/fizo_pos_catalogue.html"):
            with self.subTest(name=name):
                get_template(name)

    def test_existing_order_forms_and_basket_remain(self):
        root=Path(__file__).resolve().parent
        parent=(root/"templates/staff/order_detail.html").read_text(encoding="utf-8")
        retail=(root/"templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        cards=(root/"templates/staff/includes/fizo_pos_catalogue.html").read_text(encoding="utf-8")
        self.assertIn("fizo-checkout-catalogue",parent)
        self.assertIn("fizo-checkout-basket",parent)
        self.assertIn('value="record_payment"',parent)
        self.assertIn('value="scan_add_line"',retail)
        self.assertIn("retail-fast-checkout",retail)
        self.assertIn('event.key === "F3"',retail)
        self.assertIn("staff-orders",retail)
        self.assertIn("data-pos-menu-tile",cards)
        self.assertIn('value="add_line"',cards)
        self.assertIn("data-fizo-add-line-form",cards)
        self.assertIn("{% csrf_token %}",cards)
        self.assertIn("{% csrf_token %}",retail)
        self.assertIn("{% if is_supermarket_outlet %}",parent)

    def test_visual_basket_keeps_authorized_stock_updates(self):
        root = Path(__file__).resolve().parent
        page = (root/"templates/staff/order_detail.html").read_text(encoding="utf-8")
        retail = (root/"templates/staff/order_detail_supermarket.html").read_text(encoding="utf-8")
        self.assertIn("fizo-retail-basket-row", page)
        self.assertIn("data-fizo-qty-form", page)
        self.assertIn('value="adjust_line_qty"', page)
        self.assertIn('value="void_line"', page)
        self.assertIn('name="reason"', page)
        self.assertIn("{% csrf_token %}", page)
        self.assertIn("data-fizo-step", retail)
        self.assertIn("form.requestSubmit()", retail)
