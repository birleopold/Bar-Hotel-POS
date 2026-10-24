"""Inventory Fizo screen contracts. Browser and DB flows require separate acceptance."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse

class FizoInventoryWorkflowTests(SimpleTestCase):
    def test_setup_wizard_uses_canonical_setup_stylesheet(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / "console/templates/console/org/setup_wizard.html").read_text(encoding="utf-8")
        shell = (root / "console/templates/console/base.html").read_text(encoding="utf-8")
        ctx = (root / "console/context_processors.py").read_text(encoding="utf-8")
        setup_css = (root / "staff/static/staff/fizo-setup-area.css").read_text(encoding="utf-8")
        self.assertNotIn("fizo-setup-wizard.css", page)
        self.assertIn("fizo-setup-area.css", shell)
        self.assertIn('path.startswith("/console/org/")', ctx)
        self.assertIn(".fizo-setup-page", setup_css)
        self.assertFalse((root / "staff/static/staff/fizo-setup-wizard.css").exists())
        get_template("console/org/setup_wizard.html")

    def test_inventory_headings_use_active_tenant_not_test_tenant_brand(self):
        root = Path(__file__).resolve().parent
        for filename in ("balances", "movements", "movement_upload", "batches",
                         "intelligence", "movement_form", "scale_labels", "shelves"):
            with self.subTest(filename=filename):
                source = (root / "templates/staff/inventory" / (filename + ".html")).read_text(encoding="utf-8")
                self.assertIn('request.tenant.name|default:"Business"', source)
                self.assertNotIn('Fizo / {{ staff_product.workspace_label', source)

    def test_org_overview_does_not_display_test_tenant_brand(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "console/templates/console/org/overview.html").read_text(encoding="utf-8")
        self.assertIn('request.tenant.name|default:"Business"', source)
        self.assertNotIn("Fizo / Business management", source)
        get_template("console/org/overview.html")

    def test_console_navigation_uses_actual_tenant_brand(self):
        root = Path(__file__).resolve().parents[1] / "console/templates/console/includes"
        nav = (root / "fizo_nav.html").read_text(encoding="utf-8")
        sidebar = (root / "fizo_sidebar.html").read_text(encoding="utf-8")
        self.assertIn('console_active_tenant.name|default:"Business workspace"', nav)
        self.assertIn('console_active_tenant.name|default:"Business workspace"', sidebar)
        self.assertNotIn('default:"Fizo business"', nav)
        self.assertNotIn('</span>Fizo</a>', sidebar)

    def test_stock_balances_uses_canonical_inventory_css(self):
        root = Path(__file__).resolve().parent
        page = (root / "templates/staff/inventory/balances.html").read_text(encoding="utf-8")
        styles = (root / "static/staff/fizo-inventory-workflows.css").read_text(encoding="utf-8")
        self.assertIn("fizo-inventory-workflows.css", page)
        self.assertNotIn("fizo-stock.css", page)
        self.assertIn(".fizo-stock", styles)
        self.assertFalse((root / "static/staff/fizo-stock.css").exists())
        get_template("staff/inventory/balances.html")

    def test_three_individual_pages_compile(self):
        for name in ("movements.html", "batches.html", "movement_form.html"):
            with self.subTest(name=name):
                get_template("staff/inventory/" + name)
        for route in ("staff-inventory-movements", "staff-inventory-batches",
                      "staff-inventory-movement-create", "staff-inventory-movement-upload"):
            self.assertTrue(reverse(route).startswith("/staff/"))

    def test_shared_inventory_pages_follow_active_business(self):
        root = Path(__file__).resolve().parent / "templates/staff/inventory"
        for name in ("balances.html", "batches.html", "intelligence.html", "movement_form.html", "movements.html", "movement_upload.html", "scale_labels.html", "shelves.html"):
            with self.subTest(name=name):
                source = (root / name).read_text(encoding="utf-8")
                self.assertIn('staff_product.workspace_label|default:"Business"', source)
                self.assertNotIn("Fizo / Supermarket / Inventory", source)
                get_template("staff/inventory/" + name)

    def test_real_transaction_controls_preserved(self):
        root = Path(__file__).resolve().parent
        directory = root / "templates/staff/inventory"
        for name in ("movements.html", "batches.html", "movement_form.html"):
            with self.subTest(name=name):
                text = (directory / name).read_text(encoding="utf-8")
                self.assertIn("fizo-inventory-workflows.css", text)
                self.assertIn("fizo-inventory__header", text)
                self.assertEqual(text.count("{% block "), text.count("{% endblock %}"))
        batches = (directory / "batches.html").read_text(encoding="utf-8")
        for action in ("receive_batch", "label_existing"):
            self.assertIn('value="' + action + '"', batches)
        self.assertIn("can_modify_inventory", batches)
        self.assertIn("batch_status", batches)
        self.assertIn("batch_query", batches)
        self.assertEqual(batches.count('<form '), batches.count('{% csrf_token %}') + 1)
        movement = (directory / "movement_form.html").read_text(encoding="utf-8")
        self.assertIn("{% for field in form %}", movement)
        self.assertIn('value="create_tracked_item"', movement)
        self.assertEqual(movement.count('<form '), movement.count('{% csrf_token %}'))
        self.assertTrue((root / "static/staff/fizo-inventory-workflows.css").exists())
