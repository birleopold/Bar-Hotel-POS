# Retail R8 Hardware, Training and Rollout Acceptance Register — 2026-10-27

This register closes source implementation for R8 while keeping **software evidence** separate from **physical/on-site certification**. A checked-in implementation, green SQLite suite, or configured device label is not proof that a real printer, scanner, drawer, scale, browser or customer display worked.

## Status vocabulary

- **SOURCE IMPLEMENTED** — code, UI, migrations and regression contracts exist.
- **AUTOMATED VERIFIED** — exact-head CI/test evidence passed for the stated software boundary.
- **STAGING VERIFIED** — exact-commit PostgreSQL/browser/restore/rollback evidence was collected in isolated staging.
- **PHYSICAL VERIFIED** — named real device/model was tested on site for the exact commit.
- **PENDING** — required evidence has not yet been collected.

## R8.1 Hardware

| Capability | Source status | Automated evidence | Physical evidence required before advertising |
|---|---|---|---|
| Workstation device registry + RLS | SOURCE IMPLEMENTED | tenant/adaptor/RLS tests | none beyond staging PostgreSQL |
| Browser receipt print fallback | SOURCE IMPLEMENTED | template + observed-check contract | receipt printer model, browser/version, real print |
| Local bridge receipt printer | SOURCE IMPLEMENTED | bridge auth/queue/retry/idempotency | printer model/firmware, successful test slip and real receipt |
| Kitchen printer command | SOURCE IMPLEMENTED | bridge command compatibility | printer model/firmware and real kitchen ticket when hospitality hardware is in release scope |
| Cash drawer | SOURCE IMPLEMENTED | post-commit cash payment queues one idempotent command; diagnostics cannot open drawer | drawer + printer/bridge wiring, cash-sale open, non-cash no-open |
| Barcode scanner | SOURCE IMPLEMENTED | keyboard-wedge/browser contract + burst timing/count evidence regression; diagnostic proves no Order/device-command side effect and stores no barcode value | scanner model, rapid multi-item scan, alternating products, no lost scans |
| Weighing scale read/tare | SOURCE IMPLEMENTED | command compatibility + diagnostics | scale model, zero/tare/read with known weight |
| Customer display | SOURCE IMPLEMENTED | tenant/current-basket/privacy tests | display/browser model, live basket mirroring, tender/change, next-customer clearing |
| Retry/health/status | SOURCE IMPLEMENTED | bounded retry, offline/degraded/recovery tests | unplug/reconnect drill on bridge hardware |
| Card/mobile-money hardware | DEFERRED | provider not selected | do not advertise as integrated |

## R8.2 Training

| Requirement | Status | Evidence |
|---|---|---|
| Immutable isolated training tenant type | SOURCE IMPLEMENTED | platform-form regression |
| Staff/Console/customer-display training banners | SOURCE IMPLEMENTED | template/controller regressions |
| Retail sample products/customer/stock/sale/PO/return | SOURCE IMPLEMENTED | deterministic sample-pack tests |
| Guided cashier/storekeeper/manager checklist | SOURCE IMPLEMENTED | training controller/UI |
| Password + typed safe reset | SOURCE IMPLEMENTED | reset preservation tests |
| Preserve users/domains/outlets/workstations/hardware config | SOURCE IMPLEMENTED | reset regression |
| Block EFRIS in training | SOURCE IMPLEMENTED | fiscal guard regression |
| Block local hardware commands in training | SOURCE IMPLEMENTED | hardware guard regression |
| Hospitality training pack | PENDING / separate future pack | do not mix into retail reset |

## R8.3 Release acceptance

The exact-commit release certificate at `tools/release_certificate.py` is the gate. It must fail if mandatory evidence is absent or for another commit.

### PostgreSQL evidence coverage

`coverage` must contain: `postgresql`, `tenant_rls`, `multi_register_concurrency`, `settlement_idempotency`, `inventory_concurrency`.

### Browser evidence coverage

`coverage` must contain: `desktop`, `laptop`, `tablet`, `phone`, `keyboard`, `touch`, `scanner_input`.

Record actual browser names/versions, screen sizes and representative cashier/storekeeper/manager journeys.

### Backup/restore evidence coverage

`coverage` must contain: `backup`, `restore`, `data_consistency`.

### Rollback evidence coverage

`coverage` must contain: `git_revision`, `migrations`, `static_assets`, `service_restart`.

### Physical hardware evidence coverage

When the release advertises retail hardware, run the certificate with `--require-hardware`. `coverage` must contain: `receipt_printer`, `barcode_scanner`, `cash_drawer`, `weighing_scale`, `customer_display`.

The evidence must name actual device models/firmware or browser/display details and include concrete steps/results. Do not mark **PHYSICAL VERIFIED** from a browser capability, device label, mock or bridge queue result.

## Evidence file example

```json
{
  "commit": "<exact 40-char SHA>",
  "passed": true,
  "tested_at": "2026-10-27T21:00:00+03:00",
  "environment": "isolated staging, PostgreSQL 16, Firefox 158",
  "coverage": ["desktop", "laptop", "tablet", "phone", "keyboard", "touch", "scanner_input"],
  "steps": [
    {"name": "Cashier desktop keyboard/scanner journey", "result": "passed"},
    {"name": "Tablet touch checkout/hold/resume", "result": "passed"},
    {"name": "Phone management/report check", "result": "passed"}
  ]
}
```

## Current closeout

- R8.1: **SOURCE IMPLEMENTED; PHYSICAL VERIFICATION PENDING**.
- R8.2 Retail: **SOURCE IMPLEMENTED; exact-head automated verification pending until CI completes**.
- R8.3: **NOT CERTIFIED** until exact-commit PostgreSQL, browser, restore, rollback and required hardware evidence are collected and the release certificate reports PASS.
