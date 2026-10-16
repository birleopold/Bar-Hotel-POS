#!/usr/bin/env python3
"""Generate a conservative, source-linked snapshot of the 34-phase roadmap.

Finding a filename is only evidence of a source component, NOT proof that the
feature is usable, secure, working, tested, or production-certified.
"""
from __future__ import annotations
import argparse
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs/SUITE_IMPLEMENTATION_TODO.md"
DEFAULT_OUTPUT = ROOT / "docs/CAPABILITY_MATRIX.md"
PHASE_PATTERN = re.compile(r"^- \[([ x-])\] \*\*(\d{2}) ([^*]+):\*\*")
HINTS = {
    "01": ("workstation", "shift"),
    "02": ("dashboard", "workbench"),
    "03": ("exception", "management"),
    "04": ("handover", "drawer"),
    "05": ("customer",),
    "06": ("loyalty", "reward"),
    "07": ("insight", "intelligence"),
    "08": ("batch", "fefo"),
    "09": ("purchasing", "supplier"),
    "10": ("business_date",),
    "11": ("night_audit", "night-audit"),
    "12": ("housekeeping",),
    "13": ("kds", "kitchen"),
    "14": ("events",),
    "15": ("workstation_test", "hardware"),
    "16": ("offline",),
    "17": ("efris",),
    "18": ("analytics", "dashboard_insights"),
    "19": ("report",),
    "20": ("permissions",),
    "21": ("approval",),
    "22": ("audit",),
    "23": ("density",),
    "24": ("command",),
    "25": ("search",),
    "26": ("notification", "alerts"),
    "27": ("onboarding", "setup"),
    "28": ("demo", "training"),
    "29": ("modules", "subscription"),
    "30": ("capability_matrix",),
    "31": ("release_certificate",),
    "32": ("reconciliation", "finance"),
    "33": ("deployment", "operations"),
    "34": ("commercial_source",),
}


def matching(paths, hints, kind):
    def accept(p):
        t = p.lower()
        if not any(h in t for h in hints):
            return False
        if kind == "backend":
            return p.startswith("backend/apps/") and "/templates/" not in p and "/static/" not in p and not p.endswith(".pyc")
        if kind == "staff":
            return p.startswith("backend/apps/staff/templates/") or p.startswith("backend/apps/staff/static/")
        if kind == "api":
            return p.startswith("backend/apps/") and any(x in p for x in ("/views.py", "_views.py", "/serializers.py", "/urls.py"))
        if kind == "tests":
            return p.startswith("backend/tests/") and p.endswith(".py")
        return False
    return sorted(p for p in paths if accept(p))[:3]


def cite_paths(paths):
    if not paths:
        return "No matching source filename"
    return "<br>".join(f"[`{path.split('/')[-1]}`](../{path})" for path in paths)


def generate():
    phases = {}
    for line in ROADMAP.read_text(encoding="utf-8").splitlines():
        match = PHASE_PATTERN.match(line)
        if match:
            status, number, label = match.groups()
            phases[number] = ({"x": "Implemented (roadmap)", "-": "In progress", " ": "Pending"}[status], label)
    paths = sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in ROOT.rglob("*")
        if p.is_file()
        and ".git" not in p.parts
        and ".venv" not in p.parts
        and "node_modules" not in p.parts
        and "release-evidence" not in p.parts
    )
    header = [
        "# Capability implementation matrix",
        "",
        "Generated from `docs/SUITE_IMPLEMENTATION_TODO.md` and filenames in this checkout.",
        "",
        "**Important:** The roadmap status is the declared implementation state, not an independent test result. "
        "Filenames mean only that related source *may exist*; they are not evidence of functionality or permission coverage. "
        "PostgreSQL, real-browser and physical-device readiness must be certified separately.",
        "",
        "| Phase | Capability | Roadmap | Related backend files | Related staff/UI files | Possible API files | Matching test files | PostgreSQL / RLS | Browser / mobile | Hardware |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for number in sorted(phases):
        status, title = phases[number]
        hints = HINTS.get(number, ())
        columns = [
            number, title.replace("|", "\\|"), status,
            cite_paths(matching(paths, hints, "backend")),
            cite_paths(matching(paths, hints, "staff")),
            cite_paths(matching(paths, hints, "api")),
            cite_paths(matching(paths, hints, "tests")),
            "Not certified", "Not certified", "Not certified",
        ]
        header.append("| " + " | ".join(columns) + " |")
    header += [
        "",
        "## Interpreting these columns",
        "",
        "- **Related source:** filename matching only; it can miss implemented features when names differ, or list unrelated files with similar names. Inspect behavior and acceptance criteria directly.",
        "- **API:** possible API source filenames, not proof of a route, contract or authorization checks.",
        "- **Matching tests:** test filenames; no claim those tests passed or cover the entire feature.",
        "- **External evidence:** no certification inferred from code or historical CI. Follow `docs/RELEASE_CERTIFICATION.md`.",
        "- **Update:** `python tools/generate_capability_matrix.py` from the repository root.",
        "",
    ]
    return "\n".join(header)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="Exit nonzero if the committed matrix differs")
    args = parser.parse_args()
    content = generate()
    target = args.output.resolve()
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            print(f"Matrix is outdated: {target}")
            return 1
        print(f"Matrix is current: {target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"Capability matrix written: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
