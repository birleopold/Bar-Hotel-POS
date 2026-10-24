"""Non-destructive fixture checks for the P00 stylesheet dependency audit."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("audit_css_dependencies.py")
spec = importlib.util.spec_from_file_location("audit_css_dependencies", SCRIPT)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class CssDependencyAuditTests(unittest.TestCase):
    def test_canonical_and_missing_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "backend/apps/staff/static/staff"
            base.mkdir(parents=True)
            valid = base / "fizo-fresh.css"
            valid.write_text("body { color: #123; }", encoding="utf-8")
            template = root / "backend/apps/staff/templates/staff/test.html"
            template.parent.mkdir(parents=True)
            template.write_text(
                """{% load static %}
<link rel="stylesheet" href="{% static 'staff/fizo-fresh.css' %}">
<link rel="stylesheet" href="{% static 'staff/old-missing.css' %}">
<link rel="stylesheet" href="/static/staff/old-other.css?v=1">
""", encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                failed = audit_module.audit(root=root, files=[valid, template])
            report = json.loads(stream.getvalue())
            self.assertTrue(failed)
            self.assertEqual(report["tracked_css_count"], 1)
            self.assertEqual({x["asset"] for x in report["missing_references"]},
                             {"staff/old-missing.css", "/static/staff/old-other.css"})
            self.assertEqual(report["unreferenced_css_candidates"], [])
            self.assertEqual(len(report["hardcoded_static_css_references"]), 1)

    def test_duplicate_and_inherited_template_css_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            style = root / "backend/apps/staff/static/staff/shared.css"
            style.parent.mkdir(parents=True)
            style.write_text("body { color: black; }", encoding="utf-8")
            directory = root / "backend/apps/staff/templates/staff"
            directory.mkdir(parents=True)
            parent = directory / "base.html"
            parent.write_text(
                """{% load static %}
<link rel="stylesheet" href="{% static 'staff/shared.css' %}">
""", encoding="utf-8",
            )
            child = directory / "checkout.html"
            child.write_text(
                """{% extends "staff/base.html" %}
{% include "staff/absent.html" %}
{% include dynamic_partial %}
{% load static %}
<link rel="stylesheet" href="{% static 'staff/shared.css' %}">
<link rel="stylesheet" href="{% static 'staff/shared.css' %}">
<link rel="stylesheet" href="{% static 'staff/missing.css' %}">
""", encoding="utf-8",
            )
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(io.StringIO()):
                failed = audit_module.audit(root=root, files=[style, parent, child])
            report = json.loads(stream.getvalue())
            self.assertTrue(failed)
            self.assertEqual(
                [item["asset"] for item in report["missing_references"]],
                ["staff/missing.css"],
            )
            self.assertEqual(
                [item["asset"] for item in report["duplicate_stylesheets_in_same_source"]],
                ["staff/shared.css"],
            )
            checkout = "backend/apps/staff/templates/staff/checkout.html"
            self.assertIn("staff/shared.css", report["template_css_candidates"][checkout])
            self.assertIn(checkout, report["dynamic_template_edges"])
            self.assertTrue(any(
                edge["target"] == "staff/base.html"
                and edge["resolved_path"] == "backend/apps/staff/templates/staff/base.html"
                for edge in report["literal_template_edges"]
            ))
            self.assertTrue(any(
                edge["target"] == "staff/absent.html"
                for edge in report["unresolved_template_edges"]
            ))
            self.assertEqual(report["unreferenced_css_candidates"], [])

    def test_imports_detect_quoted_unquoted_and_query_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "backend/apps/staff/static/staff"
            base.mkdir(parents=True)
            primary = base / "primary.css"
            existing = base / "existing.css"
            existing.write_text("body { display: block; }", encoding="utf-8")
            primary.write_text(
                '@import "existing.css";\n'
                '@import url(missing-unquoted.css);\n'
                '@import url("missing-quoted.css?v=1");\n'
                '@import url(https://example.com/external.css);\n',
                encoding="utf-8",
            )
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                failed = audit_module.audit(root=root, files=[primary, existing])
            report = json.loads(stream.getvalue())
            self.assertTrue(failed)
            self.assertEqual(
                {item["asset"] for item in report["missing_references"]},
                {"missing-unquoted.css", "missing-quoted.css"},
            )
            self.assertIn(
                "backend/apps/staff/static/staff/existing.css",
                report["literal_staff_css_consumers"],
            )

    def test_python_fixture_tags_are_not_live_web_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "scripts/test_dummy.py"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                'SAMPLE = "{% static \'staff/deliberately-absent.css\' %}"',
                encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                failed = audit_module.audit(root=root, files=[fixture])
            self.assertFalse(failed)
            self.assertEqual(json.loads(stream.getvalue())["missing_references"], [])

    def test_local_untracked_css_does_not_mask_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "backend/apps/staff/static/staff"
            base.mkdir(parents=True)
            untracked = base / "missing.css"
            untracked.write_text("body {}", encoding="utf-8")
            template = root / "backend/apps/staff/templates/staff/test.html"
            template.parent.mkdir(parents=True)
            template.write_text(
                """{% load static %}<link href="{% static 'staff/missing.css' %}" rel="stylesheet">""",
                encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                failed = audit_module.audit(root=root, files=[template])
            self.assertTrue(failed)
            self.assertEqual(json.loads(stream.getvalue())["missing_references"][0]["asset"],
                             "staff/missing.css")


if __name__ == "__main__":
    unittest.main()
