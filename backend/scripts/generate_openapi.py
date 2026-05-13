"""
Export the live OpenAPI 3 schema (drf-spectacular) to docs/openapi.yaml.

Run from repo root:  python backend/scripts/generate_openapi.py
Run from backend/:    python scripts/generate_openapi.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
OUT = REPO / "docs" / "openapi.yaml"


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    cmd = [
        sys.executable,
        str(BACKEND / "manage.py"),
        "spectacular",
        "--file",
        str(OUT),
        "--validate",
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=BACKEND, check=True)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
