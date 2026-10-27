#!/usr/bin/env python3
"""Commit-bound Bar-Hotel-POS release evidence runner.

Run this ONLY on an isolated release checkout or staging environment with
the production configuration. A green SQLite suite alone cannot certify a
multi-tenant POS. Never changes live branch, services or production data.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone


ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def command(args, *, cwd=ROOT, env=None, timeout=1800):
    try:
        run = subprocess.run(
            args, cwd=cwd, env=env, capture_output=True,
            text=True, timeout=timeout, check=False,
        )
        return {
            "passed": run.returncode == 0,
            "exit_code": run.returncode,
            "stdout_tail": run.stdout[-6000:],
            "stderr_tail": run.stderr[-6000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "error": type(exc).__name__ + ": " + str(exc)[:400]}


def evidence_file(path, commit, requirement, required_coverage=()):
    if not path:
        return {"passed": False, "requirement": requirement, "reason": "Evidence file was not supplied"}
    try:
        evidence = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"passed": False, "requirement": requirement, "reason": str(exc)[:400]}
    coverage = {
        str(item).strip().lower()
        for item in (evidence.get("coverage") or [])
        if str(item).strip()
    } if isinstance(evidence, dict) else set()
    required = {str(item).strip().lower() for item in required_coverage}
    missing = sorted(required - coverage)
    valid = (
        isinstance(evidence, dict)
        and evidence.get("commit") == commit
        and evidence.get("passed") is True
        and bool(evidence.get("tested_at"))
        and bool(evidence.get("environment"))
        and isinstance(evidence.get("steps"), list)
        and bool(evidence.get("steps"))
        and not missing
    )
    reason = None
    if not valid:
        if missing:
            reason = "Missing required coverage: " + ", ".join(missing)
        else:
            reason = (
                "Require a successful evidence JSON with this exact commit, "
                "tested_at, environment, non-empty steps and required coverage."
            )
    return {
        "passed": valid,
        "requirement": requirement,
        "source": str(path),
        "coverage": sorted(coverage),
        "required_coverage": sorted(required),
        "missing_coverage": missing,
        "reason": reason,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--python", default=sys.executable, help="Python interpreter with backend dependencies")
    ap.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "release-evidence")
    ap.add_argument("--postgres-evidence", type=pathlib.Path,
                    help="Commit-bound PostgreSQL, RLS and concurrency test evidence JSON")
    ap.add_argument("--browser-evidence", type=pathlib.Path,
                    help="Commit-bound desktop, tablet, mobile and keyboard workflow evidence JSON")
    ap.add_argument("--restore-evidence", type=pathlib.Path,
                    help="Commit-bound staging backup and restore drill evidence JSON")
    ap.add_argument("--rollback-evidence", type=pathlib.Path,
                    help="Commit-bound migration and deployment rollback review evidence JSON")
    ap.add_argument("--hardware-evidence", type=pathlib.Path,
                    help="Commit-bound device/printer/cash-drawer checks when applicable")
    ap.add_argument("--require-hardware", action="store_true",
                    help="Require real-device certification for a hardware-enabled release")
    args = ap.parse_args()

    identity = command(["git", "rev-parse", "--verify", "HEAD"])
    commit = identity.get("stdout_tail", "").strip() if identity.get("passed") else ""
    clean = command(["git", "status", "--porcelain", "--untracked-files=no"])
    is_clean = clean.get("passed") and not clean.get("stdout_tail", "").strip()
    summary = {
        "format": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit, "worktree_clean": bool(is_clean),
        "python": args.python, "checks": {},
        "status": "FAIL",
        "note": "This certificate only reports evidence actually executed or supplied.",
    }
    if not commit or not is_clean:
        summary["checks"]["git_identity"] = {
            "passed": False, "reason": "Git commit missing or tracked checkout modified",
        }
    else:
        summary["checks"]["git_identity"] = {"passed": True}

    # Environment must be explicitly configured by the operator. Do not
    # assume production secrets or force a switch away from staging.
    env = dict(os.environ)
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
    py = args.python
    summary["checks"]["system"] = command(
        [py, "manage.py", "check", "--deploy"], cwd=BACKEND, env=env,
    )
    summary["checks"]["migration_drift"] = command(
        [py, "manage.py", "makemigrations", "--check", "--dry-run"],
        cwd=BACKEND, env=env,
    )
    summary["checks"]["migration_applied"] = command(
        [py, "manage.py", "migrate", "--check"],
        cwd=BACKEND, env=env,
    )
    summary["checks"]["tests"] = command(
        [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=BACKEND, env=env, timeout=3600,
    )
    summary["checks"]["static_files"] = command(
        [py, "manage.py", "collectstatic", "--noinput", "--dry-run"],
        cwd=BACKEND, env=env,
    )

    # These are not guessed from SQLite or claims in a Markdown report.
    evidence_requirements = (
        (
            "postgres_rls_concurrency",
            args.postgres_evidence,
            (
                "postgresql",
                "tenant_rls",
                "multi_register_concurrency",
                "settlement_idempotency",
                "inventory_concurrency",
            ),
        ),
        (
            "browser_responsiveness_accessibility",
            args.browser_evidence,
            (
                "desktop",
                "laptop",
                "tablet",
                "phone",
                "keyboard",
                "touch",
                "scanner_input",
            ),
        ),
        (
            "backup_restore_drill",
            args.restore_evidence,
            ("backup", "restore", "data_consistency"),
        ),
        (
            "deployment_rollback_review",
            args.rollback_evidence,
            ("git_revision", "migrations", "static_assets", "service_restart"),
        ),
    )
    for name, value, coverage in evidence_requirements:
        summary["checks"][name] = evidence_file(
            value,
            commit,
            name,
            required_coverage=coverage,
        )

    if args.require_hardware:
        summary["checks"]["physical_hardware"] = evidence_file(
            args.hardware_evidence,
            commit,
            "physical_hardware",
            required_coverage=(
                "receipt_printer",
                "barcode_scanner",
                "cash_drawer",
                "weighing_scale",
                "customer_display",
            ),
        )
    else:
        summary["checks"]["physical_hardware"] = {
            "passed": True, "not_applicable": True,
            "reason": "Physical hardware not included in this release scope",
        }

    summary["status"] = (
        "PASS" if all(check.get("passed") for check in summary["checks"].values())
        else "FAIL"
    )
    output_dir = args.output_dir / (commit[:12] if commit else "unknown")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "certificate.json"
    target.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Release evidence: {target}")
    print(f"Exact commit: {commit or 'unknown'}")
    print(f"Certification status: {summary['status']}")
    for name, check in summary["checks"].items():
        print(f"  {'PASS' if check.get('passed') else 'FAIL'} {name}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
