#!/usr/bin/env python3
"""Audit tracked CSS dependencies without deleting business-specific styles.

Run from the repository root:
    python scripts/audit_css_dependencies.py
Produces a JSON inventory and fails on missing literal Django static CSS links
and missing relative @import paths. Only Git-tracked assets count as present. Dynamic paths are reported for manual review.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_URL = re.compile(r"""{%\s*static\s+['"]([^'"]+\.css)['"]\s*%}""")
IMPORT = re.compile(r"""@import\s+(?:url\(\s*)?['"]([^'"]+\.css)['"]""")
DYNAMIC = re.compile(r"""{%\s*static\s+(?!['"])""")
# Also cover hardcoded CSS assets; these bypass Django's configured static URL.
RAW_CSS_URL = re.compile(r"""(?:href\s*=\s*['"])(/static/staff/[^'"?#]+\.css)(?:\?[^'"]*)?['"]""")

def tracked_files():
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]

def audit(root=ROOT, files=None):
    root = Path(root).resolve()
    files = tracked_files() if files is None else [Path(p).resolve() for p in files]
    tracked = set(files)
    css = [p for p in files if p.suffix.lower() == ".css"]
    consumers = {}
    missing = []
    dynamic = []
    hardcoded = []
    # Inspect real web assets; Python test fixtures may embed deliberately missing CSS tags.
    for src in files:
        if src.suffix.lower() not in {".html", ".css", ".js"}:
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        if DYNAMIC.search(text) and src.suffix == ".html":
            dynamic.append(str(src.relative_to(root)))
        for raw in RAW_CSS_URL.findall(text):
            hardcoded.append({"source": str(src.relative_to(root)), "asset": raw})
            rel = raw.removeprefix("/static/")
            destination = root / "backend" / "apps" / "staff" / "static" / rel
            consumers.setdefault(str(destination.relative_to(root)), []).append(str(src.relative_to(root)))
            if destination not in tracked:
                missing.append({"source": str(src.relative_to(root)), "asset": raw})
        for rel in CSS_URL.findall(text):
            destination = root / "backend" / "apps" / "staff" / "static" / rel if rel.startswith("staff/") else None
            if destination is None:
                # Django finders may resolve a stylesheet elsewhere in installed apps.
                continue
            consumers.setdefault(str(destination.relative_to(root)), []).append(str(src.relative_to(root)))
            if destination not in tracked:
                missing.append({"source": str(src.relative_to(root)), "asset": rel})
        if src.suffix == ".css":
            for uri in IMPORT.findall(text):
                if uri.startswith(("http:", "https:", "/", "//")):
                    continue
                destination = (src.parent / uri).resolve()
                if destination in tracked:
                    consumers.setdefault(str(destination.relative_to(root)), []).append(str(src.relative_to(root)))
                if destination not in tracked:
                    missing.append({"source": str(src.relative_to(root)), "asset": uri})
    consumers = {key: sorted(set(value)) for key, value in sorted(consumers.items())}
    missing.sort(key=lambda item: (item["source"], item["asset"]))
    hardcoded.sort(key=lambda item: (item["source"], item["asset"]))
    referenced = set(consumers)
    unreferenced = [str(p.relative_to(root)) for p in css if str(p.relative_to(root)) not in referenced]
    report = {
        "tracked_css_count": len(css),
        "tracked_css_files": sorted(str(p.relative_to(root)) for p in css),
        "literal_staff_css_consumers": consumers,
        "dynamic_template_static_tags": sorted(set(dynamic)),
        "missing_references": missing,
        "hardcoded_static_css_references": hardcoded,
        "unreferenced_css_candidates": sorted(unreferenced),
        "unreferenced_css_warning": "Candidate only: JS, CSS imports, computed asset names and runtime loads require tracing before deletion.",
        "hardcoded_static_css_policy": "Hardcoded /static/staff/*.css references are audited; prefer Django {% static %} in templates.",
        "note": "CSS classes used in JS and template inheritance need browser and manual verification before deleting files.",
    }
    print(json.dumps(report, indent=2))
    if missing:
        print(f"CSS dependency audit: {len(missing)} missing tracked stylesheet reference(s)", file=sys.stderr)
        for item in missing:
            print(f"  {item['source']}: {item['asset']}", file=sys.stderr)
    return bool(missing)

if __name__ == "__main__":
    sys.exit(1 if audit() else 0)
