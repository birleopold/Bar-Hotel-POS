#!/usr/bin/env python3
"""Inventory every resolved Django URL and tracked template for Fizo.

Run from backend: ../.venv/bin/python ../scripts/inventory_fizo_routes.py
Emits CSV files in the current directory. Reads Django configuration; does not
issue requests, modify data, or touch financial transactions.
"""
from __future__ import annotations

import csv
import os
import sys
import inspect
from collections import Counter
from pathlib import Path

# Executing scripts/foo.py sets sys.path[0] to scripts/, not backend/.
# Always resolve the Django project relative to this script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
import django

django.setup()
from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver


def domain(value: str) -> str:
    s = value.lower()
    if any(w in s for w in ("platform", "admin/", "audit-events", "plans")):
        return "Platform administration"
    if any(w in s for w in ("lodging", "room", "folio", "reservation", "housekeeping", "night-audit")):
        return "Hotel"
    if any(w in s for w in ("kds", "kitchen")):
        return "Restaurant / kitchen"
    if any(w in s for w in ("modifier", "menu/", "table", "recipe")):
        return "Restaurant / Bar / Shared catalogue"
    if any(w in s for w in ("inventory", "stock", "purchasing", "wholesale", "pickups", "shelves")):
        return "Supermarket / Retail / Shared stock"
    if any(w in s for w in ("service", "spa", "appointment")):
        return "Services"
    if "events" in s:
        return "Events"
    if any(w in s for w in ("finance", "report", "cashbook")):
        return "Shared finance / reporting"
    if any(w in s for w in ("auth", "login", "signup", "password", "invite", "settings", "staff/pin")):
        return "Shared authentication / settings"
    if any(w in s for w in ("orders", "pos", "payment", "shift")):
        return "Shared POS"
    if s.startswith("api/"):
        return "Shared API"
    return "Shared / cross-business"


def patterns(resolver, prefix: str = ""):
    for item in resolver.url_patterns:
        path = prefix + str(item.pattern)
        if isinstance(item, URLResolver):
            yield from patterns(item, path)
        elif isinstance(item, URLPattern):
            view = item.callback
            viewcls = getattr(view, "view_class", None)
            cls = viewcls or getattr(view, "cls", None)
            function = cls or view
            location = getattr(function, "__module__", "") + "." + getattr(function, "__qualname__", "")
            template = getattr(function, "template_name", None)
            if not isinstance(template, str):
                template = ""
            try:
                view_source = inspect.getsourcefile(function) or ""
            except (TypeError, OSError):
                view_source = ""
            namespace = "api" if path.startswith("api/") else "admin" if path.startswith("admin/") else "web"
            kind = ("API / data" if namespace == "api" else
                    "Generated admin" if namespace == "admin" else
                    "Action / service" if any(w in path.lower() for w in
                     ("logout/", "lock/", "select-", "dismiss/", "resume/", "download/", "export/")) else
                    "Visual candidate")
            yield {
                "pattern": "/" + path,
                "route_name": item.name or "",
                "view": location,
                "view_source": str(Path(view_source).resolve().relative_to(PROJECT_ROOT)) if view_source and Path(view_source).resolve().is_relative_to(PROJECT_ROOT) else "",
                "declared_template": template,
                "route_kind": kind,
                "business_line": domain(path),
                "verified": "NO",
                "notes": "Generated pattern; dynamic converters/regex are not literal URLs",
            }


root = PROJECT_ROOT
rows = list(patterns(get_resolver()))
dest = Path.cwd() / "fizo_resolved_routes.csv"
with dest.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["pattern", "route_name", "view", "view_source", "declared_template", "route_kind", "business_line", "verified", "notes"])
    writer.writeheader()
    writer.writerows(rows)

html_paths = sorted(root.glob("backend/**/*.html"))
templates = []
for file in html_paths:
    p = file.relative_to(root).as_posix()
    kind = "Included/shared" if "/includes/" in p or p.endswith("/base.html") else "Screen/other"
    templates.append({"template": p, "business_line": domain(p), "kind": kind, "verified": "NO"})
with (Path.cwd() / "fizo_templates.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=["template", "business_line", "kind", "verified"])
    writer.writeheader()
    writer.writerows(templates)

print("Resolved URL patterns:", len(rows), "=>", dest)
print("Tracked template files:", len(templates), "=>", Path.cwd() / "fizo_templates.csv")
# One row per potential human-facing screen, cross-referenced to its view.
# Template resolution can be dynamic (e.g. outlet-dependent checkouts). Such
# routes are flagged for manual tracing rather than assigned a guessed file.
visual_rows = [r for r in rows if r["route_kind"] == "Visual candidate"]
for row in visual_rows:
    row["template_match"] = "Declared" if row["declared_template"] else "NEEDS VIEW TRACE"
    row["redesign_status"] = "NOT VERIFIED"
visual_file = Path.cwd() / "fizo_visual_screen_register.csv"
with visual_file.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=[
        "pattern", "route_name", "view", "view_source", "declared_template",
        "template_match", "business_line", "redesign_status",
    ], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(visual_rows)

print("Visual candidates:", len(visual_rows), "=>", visual_file)
print("Template links requiring trace:",
      sum(not row["declared_template"] for row in visual_rows))
print("Classification:", dict(Counter(r["route_kind"] for r in rows)))
print("Includes Django admin, DRF router actions, and dynamic URL patterns.")
