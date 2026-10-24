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
# Accept quoted @import, url("file.css"), and url(file.css) with optional query strings.
IMPORT = re.compile(r"""@import\s+(?:url\(\s*)?['"]?([^'"\s)]+\.css)(?:\?[^'"\s)]*)?['"]?""")
DYNAMIC = re.compile(r"""{%\s*static\s+(?!['"])""")
# Also cover hardcoded CSS assets; these bypass Django's configured static URL.
RAW_CSS_URL = re.compile(r"""(?:href\s*=\s*['"])(/static/staff/[^'"?#]+\.css)(?:\?[^'"]*)?['"]""")

# Explicit Django inheritance/include edges only; conditional includes are
# candidates, not proof the files render together at runtime.
TEMPLATE_EDGE = re.compile(r"""{%\s*(extends|include)\s+['"]([^'"]+)['"]""")
TEMPLATE_DYNAMIC_EDGE = re.compile(r"""{%\s*(?:extends|include)\s+(?!['"])""")

def tracked_files():
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]

def audit(root=ROOT, files=None):
    root = Path(root).resolve()
    files = tracked_files() if files is None else [Path(p).resolve() for p in files]
    tracked = set(files)
    css = [p for p in files if p.suffix.lower() == ".css"]
    consumers = {}
    template_edges = []
    literal_css_by_source = {}
    dynamic_template_edges = []
    template_names = {}
    for src in files:
        if src.suffix == ".html" and "templates" in src.parts:
            marker = src.parts.index("templates")
            template_names["/".join(src.parts[marker + 1:])] = src
    repeated_in_source = []
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
        if src.suffix == ".html":
            source_name = str(src.relative_to(root))
            for relation, target in TEMPLATE_EDGE.findall(text):
                destination = template_names.get(target)
                template_edges.append({
                    "source": source_name, "relation": relation,
                    "target": target,
                    "resolved_path": str(destination.relative_to(root)) if destination else None,
                })
            if TEMPLATE_DYNAMIC_EDGE.search(text):
                dynamic_template_edges.append(source_name)
        if DYNAMIC.search(text) and src.suffix == ".html":
            dynamic.append(str(src.relative_to(root)))
        seen_in_source = set()
        # A stylesheet repeated by the same template is a CSS owner conflict.
        # Record exact duplicates only; inheritance and dynamic includes need
        # separate browser tracing before any stylesheet is removed.
        literal_refs = [value for value in CSS_URL.findall(text)]
        literal_refs += [raw.removeprefix("/static/") for raw in RAW_CSS_URL.findall(text)]
        if src.suffix == ".html":
            literal_css_by_source[str(src.relative_to(root))] = sorted(set(literal_refs))
        for ref in literal_refs:
            if ref in seen_in_source and src.suffix == ".html":
                repeated_in_source.append({"source": str(src.relative_to(root)), "asset": ref})
            seen_in_source.add(ref)
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
    repeated_in_source.sort(key=lambda item: (item["source"], item["asset"]))
    hardcoded.sort(key=lambda item: (item["source"], item["asset"]))
    referenced = set(consumers)
    unreferenced = [str(p.relative_to(root)) for p in css if str(p.relative_to(root)) not in referenced]
    # A literal reference audit cannot prove an asset is unused: Django
    # template inheritance, generated paths and browser-loaded styles remain.
    # Keep candidates informational; never auto-delete or auto-merge them.
    # Enumerate potential CSS ownership through literal extends/includes.
    # This is a source dependency graph, NOT evidence that conditional
    # branches actually render together.
    resolved_edges = {}
    for edge in template_edges:
        if edge["resolved_path"]:
            resolved_edges.setdefault(edge["source"], set()).add(edge["resolved_path"])

    def stylesheet_candidates(template, visiting):
        if template in visiting:
            return set()
        refs = set(literal_css_by_source.get(template, ()))
        for dependency in resolved_edges.get(template, ()):
            refs.update(stylesheet_candidates(dependency, visiting | {template}))
        return refs

    template_css_candidates = {
        template: sorted(stylesheet_candidates(template, set()))
        for template in sorted(literal_css_by_source)
    }
    unresolved_template_edges = [
        edge for edge in template_edges if edge["resolved_path"] is None
    ]
    report = {
        "tracked_css_count": len(css),
        "tracked_css_files": sorted(str(p.relative_to(root)) for p in css),
        "literal_staff_css_consumers": consumers,
        "dynamic_template_static_tags": sorted(set(dynamic)),
        "missing_references": missing,
        "literal_template_edges": sorted(template_edges, key=lambda edge: (edge["source"], edge["relation"], edge["target"])),
        "template_css_candidates": template_css_candidates,
        "unresolved_template_edges": sorted(unresolved_template_edges, key=lambda edge: (edge["source"], edge["relation"], edge["target"])),
        "dynamic_template_edges": sorted(set(dynamic_template_edges)),
        "template_relationship_warning": "Explicit edges are candidates only; conditional includes, blocks and runtime template selection need browser tracing.",
        "duplicate_stylesheets_in_same_source": repeated_in_source,
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
