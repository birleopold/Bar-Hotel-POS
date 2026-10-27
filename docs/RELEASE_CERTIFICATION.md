# Release certification (Phase 31)

This repository's GitHub Actions SQLite checks are **not** production release certification. The commit-bound runner at `tools/release_certificate.py` fails unless local Django deployment, migrations, tests, and static-file checks succeed **and** the release operator supplies independently collected PostgreSQL, browser, backup/restore and rollback evidence for that exact commit.

## In an isolated staging checkout

1. Checkout the precise proposed release commit; ensure tracked files are clean.
2. Configure the Python interpreter and **staging** production-like environment, PostgreSQL, Redis and any required provider sandbox. Do **not** point the tool at a live tenant database.
3. Collect the evidence described below, then run:

```bash
python tools/release_certificate.py \
  --python backend/.venv/bin/python \
  --postgres-evidence /secure/evidence/postgres.json \
  --browser-evidence /secure/evidence/browser.json \
  --restore-evidence /secure/evidence/restore.json \
  --rollback-evidence /secure/evidence/rollback.json
```

For a release that advertises integrated printers, scanners, tills or kitchen displays, also provide `--require-hardware --hardware-evidence /secure/evidence/hardware.json`.

Do not commit private evidence, production credentials or customer data. The runner writes a summary to `release-evidence/<commit-prefix>/certificate.json`, returns exit code 1 if any mandatory check fails, and reports **PASS** only for an exact-commit evidence set with all required inputs present.

## Evidence JSON contract

Each independently collected evidence document must contain at minimum:

```json
{
  "commit": "<exact 40-character Git SHA being certified>",
  "passed": true,
  "tested_at": "2026-10-27T21:00:00+03:00",
  "environment": "isolated staging / PostgreSQL version / browser or hardware versions",
  "coverage": ["<required coverage tokens for this evidence type>"],
  "steps": [
    {"name": "Scope and test", "result": "passed"}
  ]
}
```

The runner validates presence, passing status, current commit identity, testing time and environment. **It does not independently prove the truth of an external file.** Each evidence owner must retain original test traces or signed logs separately.

Required source evidence:

- **PostgreSQL:** migration state, tenant RLS read/write denial across tenants, concurrent POS settlement, FEFO stock consumption, purchase receiving, audit closing and idempotency.
- **Browsers:** actual desktop/laptop/tablet/mobile and large-display workflows; keyboard navigation, touch targets, service worker/offline behavior and accessible dialogs. Note actual browser names and versions.
- **Restore:** staging backup and restore, data consistency verification, database tooling version and exact operation times.
- **Rollback:** rehearsed deployment rollback, migration backward compatibility, transactional safety and exact git/static asset versions.
- **Hardware (when advertised):** physical printer/scanner/drawer/KDS exercises, with real device models and firmware.

The certificate also validates explicit `coverage` tokens so a generic passing file cannot stand in for missing acceptance areas. Retail requirements are:
- PostgreSQL: `postgresql`, `tenant_rls`, `multi_register_concurrency`, `settlement_idempotency`, `inventory_concurrency`.
- Browsers/input: `desktop`, `laptop`, `tablet`, `phone`, `keyboard`, `touch`, `scanner_input`.
- Restore: `backup`, `restore`, `data_consistency`.
- Rollback: `git_revision`, `migrations`, `static_assets`, `service_restart`.
- Physical retail hardware when required: `receipt_printer`, `barcode_scanner`, `cash_drawer`, `weighing_scale`, `customer_display`.

See `docs/RETAIL_R8_ACCEPTANCE_REGISTER_2026-10-27.md` for the source/automated/staging/physical status distinction.

The command does not deploy, revert code, change services or modify production records. Never say “certified” when any mandatory evidence file is absent, stale, on a different commit or not actually verified.
