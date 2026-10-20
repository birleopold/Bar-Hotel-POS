"""Branded print documents must use the tenant passed in request context."""
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase


class BrandedOrderPrintTests(SimpleTestCase):
    def test_receipt_identifies_current_business_and_footer(self):
        request = RequestFactory().get("/staff/orders/print/")
        request.tenant = SimpleNamespace(name="Sennana Supermarket")
        request.session = {}
        order = SimpleNamespace(
            bill_reference="SALE-001",
            outlet=SimpleNamespace(name="Main Register"),
            table_label="",
            currency="UGX",
            subtotal="10000",
            tax_total="0",
            total="10000",
            lines=SimpleNamespace(all=lambda: []),
        )
        html = render_to_string(
            "staff/order_print.html",
            {
                "request": request,
                "order": order,
                "document_title": "Receipt",
                "printed_at": "2026-10-21",
                "tenant_settings": SimpleNamespace(
                    logo_url="https://example.test/logo.png",
                    receipt_footer="Thank you for shopping",
                ),
                "page_size": "A4",
                "page_margin": "10mm",
                "font_size": "12px",
                "body_padding": "10px",
                "paper_width": "100%",
                "headline_size": "18px",
                "a4_only_display": "block",
                "amount_paid": "10000",
                "balance_due": "0",
                "show_payment_history": False,
                "show_refund_history": False,
            },
        )
        self.assertIn("Sennana Supermarket", html)
        self.assertIn("Thank you for shopping", html)
        self.assertIn("https://example.test/logo.png", html)
        self.assertNotIn("Kartel Bar", html)
        request.tenant = SimpleNamespace(name="Kartel Bar")
        kartel_html = render_to_string(
            "staff/order_print.html",
            {
                "request": request, "order": order,
                "document_title": "Bill", "printed_at": "2026-10-21",
                "tenant_settings": SimpleNamespace(logo_url="", receipt_footer="Visit again"),
                "page_size": "A4", "page_margin": "10mm",
                "font_size": "12px", "body_padding": "10px",
                "paper_width": "100%", "headline_size": "18px",
                "a4_only_display": "block", "amount_paid": "10000",
                "balance_due": "0", "show_payment_history": False,
                "show_refund_history": False,
            },
        )
        self.assertIn("Kartel Bar", kartel_html)
        self.assertIn("Visit again", kartel_html)
        self.assertNotIn("Sennana Supermarket", kartel_html)
        self.assertNotIn("Thank you for shopping", kartel_html)
