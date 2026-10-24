"""Source-level purchasing screen regression checks; browser acceptance separate."""
from pathlib import Path
from django.template.loader import get_template
from django.test import SimpleTestCase

class FizoPurchasingLayoutTests(SimpleTestCase):
    pages=("purchase_orders_list.html","purchase_order_create.html","purchase_order_detail.html","supplier_balances.html","supplier_form.html","suppliers_list.html")
    def test_all_seven_templates_compile(self):
        for name in (*self.pages,"includes/subnav.html"):
            with self.subTest(name=name):
                get_template("staff/purchasing/"+name)
    def test_page_templates_have_fizo_shell(self):
        base=Path(__file__).resolve().parent/"templates/staff/purchasing"
        for name in self.pages:
            with self.subTest(name=name):
                s=(base/name).read_text(encoding="utf-8")
                self.assertIn("management-workflows.css",s)
                self.assertIn("fizo-purchasing__header",s)
                self.assertIn('request.tenant.name|default:"Business"',s)
                self.assertNotIn("Fizo / Supermarket / Purchasing",s)
                self.assertEqual(s.count("{% block "),s.count("{% endblock %}"))
    def test_payment_and_supplier_forms_remain(self):
        base=Path(__file__).resolve().parent/"templates/staff/purchasing"
        po=(base/"purchase_order_detail.html").read_text(encoding="utf-8")
        self.assertEqual(po.count("<form "),po.count("{% csrf_token %}"))
        self.assertIn("po.lines.all",po)
        create=(base/"purchase_order_create.html").read_text(encoding="utf-8")
        self.assertIn("{% csrf_token %}",create)
        supplier=(base/"supplier_form.html").read_text(encoding="utf-8")
        self.assertIn("{% for field in form %}",supplier)
        self.assertIn("{% csrf_token %}",supplier)
        self.assertFalse((Path(__file__).resolve().parent/"static/staff/fizo-purchasing.css").exists())
        self.assertIn(".fizo-purchasing", (Path(__file__).resolve().parent/"static/staff/management-workflows.css").read_text(encoding="utf-8"))
