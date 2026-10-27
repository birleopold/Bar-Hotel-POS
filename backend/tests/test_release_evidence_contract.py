import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "release_certificate.py"
SPEC = importlib.util.spec_from_file_location("release_certificate_tool", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write_evidence(tmp_path, *, coverage):
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps(
            {
                "commit": "a" * 40,
                "passed": True,
                "tested_at": "2026-10-27T21:00:00+03:00",
                "environment": "isolated staging",
                "coverage": coverage,
                "steps": [{"name": "exercise", "result": "passed"}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_release_evidence_rejects_generic_pass_without_required_coverage(tmp_path):
    path = _write_evidence(tmp_path, coverage=["desktop"])
    result = MODULE.evidence_file(
        path,
        "a" * 40,
        "browser",
        required_coverage=(
            "desktop",
            "laptop",
            "tablet",
            "phone",
            "keyboard",
            "touch",
            "scanner_input",
        ),
    )
    assert result["passed"] is False
    assert result["missing_coverage"] == [
        "keyboard",
        "laptop",
        "phone",
        "scanner_input",
        "tablet",
        "touch",
    ]
    assert "Missing required coverage" in result["reason"]


def test_release_evidence_accepts_complete_exact_commit_coverage(tmp_path):
    required = (
        "receipt_printer",
        "barcode_scanner",
        "cash_drawer",
        "weighing_scale",
        "customer_display",
    )
    path = _write_evidence(tmp_path, coverage=list(required))
    result = MODULE.evidence_file(
        path,
        "a" * 40,
        "physical_hardware",
        required_coverage=required,
    )
    assert result["passed"] is True
    assert result["missing_coverage"] == []
    assert result["reason"] is None


def test_release_evidence_rejects_other_commit_even_with_complete_coverage(tmp_path):
    path = _write_evidence(
        tmp_path,
        coverage=["backup", "restore", "data_consistency"],
    )
    result = MODULE.evidence_file(
        path,
        "b" * 40,
        "restore",
        required_coverage=("backup", "restore", "data_consistency"),
    )
    assert result["passed"] is False
    assert result["missing_coverage"] == []
