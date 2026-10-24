# Codex handoff — 16 October 2026 (Africa/Kampala)

## Active incident: retail basket quantity +/− (24 October 2026)

**Correction to previous implementation report (24 October):** commit `4fe79312` accidentally changed the row lock in `apply_supermarket_line_discount` rather than `adjust_open_order_line_quantity` because the first matching query snippet was patched without verifying the enclosing function. The original PostgreSQL failing query therefore remained. Commit `0bea9ce6` reverts that unrelated discount modification and changes the exact quantity-service query. Existing `test_quantity_service_locks_nullable_product_line_without_outer_join` must be executed against PostgreSQL, then live +/− tested and amounts confirmed after reload. No certification until evidence.

**ROOT CAUSE CORRECTED IN SOURCE — awaiting deployed PostgreSQL/browser verification.** Catalogue product selection increments quantity; basket +/− previously returned 500. Production rollback-only test traced this to `select_for_update().select_related("menu_item")` in `adjust_open_order_line_quantity`: PostgreSQL disallows `FOR UPDATE` on the nullable side of an outer join. Commit `4fe79312` now locks only the order-line row with `select_for_update(of=("self",))` and reads menu_item on demand. Removed incident-only exception masking in `3ba51e69`; added the nullable service-line regression test in `09f6e502`. No extra service/view files were introduced. One confirmed defect (form.action shadowed by hidden input named action) was corrected in commit `f38aec41`, but the live checkout still returned 500. Subsequent frontend error-reporting and read-back fallbacks did **not** solve the backend failure; do not layer more on them. Review and remove superseded handling when the actual root cause is fixed. UI work must not compromise payment constraints or stock/audit correctness.

The diagnostic command `.venv/bin/python backend/manage.py shell` **ran development settings backed by SQLite**, not the production PostgreSQL configured by `deployment/contabo/deploy-app.sh`. Its `sqlite3.OperationalError: no such column: pos_order.quick_create_key` came from the local SQLite schema and occurred before the target order was loaded. **Do not migrate SQLite or interpret this as the production 500**. For the real diagnosis, first select the same environment and `DJANGO_SETTINGS_MODULE=config.settings.production` as the service using the existing `/etc/leosoft-pos/pos.env` (do not print database credentials), then verify the active database engine; obtain the production traceback for the failing POST or reproduce in a rollback-only transaction on that database. Never make a permanent change to a live basket merely to diagnose.

Owner's correction policy: failed fixes are replaced/removed, not stacked. Track eliminated code, test execution and browser evidence before closing this incident. **Quantity correction requires focused tests and live acceptance: +/−, line amount, total due and persistence after refresh. No certification yet.**

## Roadmap continuation — 24 October, P00 plus coupled P07

Roadmap signoff remains at P00, with P07 only partially implemented. The shared `process_supermarket_line_return` service contained the same PostgreSQL-invalid nullable `menu_item` join as the quantity-edit service. Commit `fed8494b` replaces its row lock within that exact return function; `e3cd7c65` adds a nullable service return regression to the existing cashier test file. No new CSS, service files, migrations or alternative handlers were added. Existing return/restock/payment validation remains in place. PostgreSQL execution, browser returns, and all-tenant authorization verification are not yet evidenced; do not mark complete.

Next execution: on disposable test database run `backend/tests/test_supermarket_cashier_lane.py` against PostgreSQL under CI settings, verify the original quantity operation and returned non-product line with correct tenant scope, then capture P00 route/CSS/visual evidence. Do not mutate production baskets to pass tests.

## P00 continuation checkpoint — 24 October (after `9aa86c6`)

- Corrected another *existing* PostgreSQL-invalid nullable related row lock, this time only inside `process_supermarket_line_return` (`fed8494b`). No duplicate services, CSS, routes or migrations.
- Extended the existing supermarket checkout test file: nullable service return (`e3cd7c65`), captured PostgreSQL SQL lock assertions on quantity and returns (`bfc77761`), and rejected cross-tenant return lines (`1c7cd8c9`). This links P00 with partial P03/P07/P15 coverage.
- **Not yet run:** focused SQLite/PostgreSQL suite or full CI against these commits; live checkout/returns and reference-image viewport acceptance. P00 remains open; P03/P07/P15 unaccepted. Do not run cross-tenant write tests against production data.
- Next: run tests in disposable DB, verify actual SQL and HTTP flows, then resume P00 CSS route/ownership trace and baseline screenshots. A failed test must drive replacement of the faulty change, not another workaround layer.

## Larger P00–P06 integrated shell bundle (24 October evening)

Directly on `origin/main` (no branches): `staff/base.html` now scopes cross-tab terminal-lock localStorage keys to tenant plus user (`c97a3d2`); the staff header POS shortcut uses the real supermarket/retail register URL rather than the sales list (`328a51a`); staff header identifies the signed-in operator (`795aa7f`, neutral wording in `8eaffc7`) with responsive rules in existing `fizo-fresh.css` (`c119a1d`). All business lines continue sharing the same template/CSS; no new feature-specific stylesheet. Regression source checks added to existing staff test file (`ad4915c`). P00 CSS dependency audit reports duplicate literal stylesheet links from the same source (`7e842a4`) without auto-deleting assets.

Acceptance still pending: actual browser tests with two accounts/tenants and terminal lock, approved screenshot comparisons at five widths, CSS audit fresh output, and SQL/CI tests. Avoid declaring P00/P02/P03/P04/P06 complete, even if code is merged. Next review the audit findings, resolve verified missing/doubled CSS at their canonical owner, and complete deployed user journeys.

## P00/P01/P02 CSS review continuation — 24 October

Worked only in existing files. `scripts/audit_css_dependencies.py` duplicate-literal reporting now only flags repeated HTML template stylesheet references (`2017ceeb`); the existing staff regression module has a disposable temporary-file test verifying duplicates, missing assets and referenced CSS (`6a020c0`). `fizo-fresh.css` has a redundant mobile room-grid breakpoint declaration removed while preserving existing 550px layout and 480px card geometry (`f4d1e402`). No new stylesheet or controller; no speculative deletion of supposedly unused assets. Roadmap acceptance remains P00 open. **No execution evidence of the new tests or fresh whole-repository audit**; do not call CSS merge or UI pixel parity complete.

## Quick start

**Latest owner direction (23 October 2026):** follow `docs/FIZO_COMPLETE_IMPLEMENTATION_ROADMAP_2026-10-23.md` sequentially. P00 is underway; see `docs/evidence/p00-2026-10-23/README.md` for the `8d45fb3` baseline, failing CI and missing asset references. Earlier checkpoint counts below are historical. No later visual phase is complete by implication.

This handoff is in the GitHub repository itself. After pulling latest main, Codex should read `AGENTS.md`, **this handoff**, `docs/SUITE_IMPLEMENTATION_TODO.md`, `docs/RELEASE_CERTIFICATION.md`, and `.github/workflows/quality.yml`. The handoff does not replace examining actual code and running tests.

```bash
git status --short
git branch --show-current
git pull --ff-only origin main
git log -5 --oneline
cd backend
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp
```

Use the local virtual environment and proper OS activation instead of system Python if one is already configured. Read `docs/INSTALLATION.md` before populating `.env` or creating a local database. Run the suite against disposable local data, never production; follow the CI workflow for environment variables.

## Original owner requirements

- Do implementation without interactive prompts, research online, keep UI and language simple, cover backend **and** front end/navigation, support mobile/tablet/desktop/large screens, avoid duplicate functionality, complete full journeys, and commit to `origin/main` autonomously.
- Maintain **Uganda-first scope**, including EFRIS only for Uganda, not foreign tax integrations.
- Owner's requested milestone: **9/34 implemented and locally verified**, then comprehensive release certification. **This milestone has not yet been attained.**

## Actual starting point

At the handoff preparation, `main` was confirmed as `31bb0fddcb456609b438bc19b9718b0ad32662ce` (before the handoff commits). All prior changes discussed were already committed to GitHub main; no uncommitted remote edits exist in a GitHub API workflow. Recheck latest head before implementation.

Authoritative checklist statuses: **4 [x] implemented/locally verified, 22 [-] in progress, 8 [ ] pending**. The completed phases are 01 Workstations, 02 Role Workspaces, 03 Manager Exceptions and 04 Shift Handover. External production certification for even these four is not established. Phases **05–09 are in progress**, not complete. Never convert them to [x] unless all original acceptance criteria and locally executed tests pass.

### Specific latest implementation changes

- Reconciliation: `backend/apps/customers/loyalty_reconciliation.py`, staff views and customer detail/list templates; account and tenant point summaries; added mock and database-level regression tests. Existing points accrual/refund policy in `docs/LOYALTY_POINTS_POLICY.md`. **Redemption/coupons/tiers, accounting liability treatment and full customer workflow are still pending.**
- Inventory and purchasing migration drift: `inventory.0009_alter_stockbatchallocation_quantity` and `purchasing.0010_alter_supplierinvoice_amount_and_more` committed to match current model definitions.
- Onboarding crash: `backend/apps/console/setup_flow.py` previously used `has_services_line` and `has_events_line` before assignment; initialized both before computing `has_pos_work`.
- Staff navigation: `backend/apps/staff/context_processors.py` and `templates/staff/includes/sidebar.html` now show quick-create order only for operational write roles rather than all staff with orders list visibility.
- Device observation security: `backend/apps/pos/services/hardware.py` refreshes tenant module rules when checking kitchen device availability.
- Scheduled reports: `backend/apps/api/owner_reports.py` refreshes stored timezone in `scheduled_period`.

These edits need repeat verification in combination; prior CI pipelines may have been cancelled due to newer pushes.

## CI evidence and failing areas

One **completed** pre-fix main run: [GitHub Actions 38902175104](https://github.com/birleopold/Bar-Hotel-POS/actions/runs/38902175104) resulted in **456 passed, 25 failed, 5 skipped**, after Django system and migration checks passed. A later `main` run for `31bb0fdd` was **pending** when checked. Recheck latest complete Actions run; never cite old failures as current after fixes.

Known failing tests from that baseline (investigate current stack traces and confirm fixes, not just assertions):

- `tests/test_critical_workflow_guards.py`: reservation status API scope/permission.
- `tests/test_folio_settlement.py`: folio API scope, dashboard setup crash, room maintenance request.
- `tests/test_invite_create_throttle.py`: site/outlet selection in invitations.
- `tests/test_offline_replay_safety.py`: same logical quantity serialized as `1.000` vs `1` on safe catalog-retry.
- `tests/test_onboarding_web_flows.py`: import UI, preview/save and practice-checkout response.
- `tests/test_role_workspaces.py`: reception create-order shortcut and storekeeper receiving queue.
- `tests/test_scheduled_owner_reports.py`: timezone period calculation and email delivery/retry.
- `tests/test_workstation_hardware_observations.py`: kitchen device availability for retail-only tenant.
- `apps/console/tests.py`: setup skip/reset and prerequisites screens.
- `apps/staff/tests.py`: owner setup CTA, hotel dashboard, audit view scope, cleaner room status, refund error feedback and read-only tables.

Do not change tests only to make green. Understand intended business behavior, fix broken views/services and preserve scope/security. Add targeted tests where needed; run full suite to catch regressions.

## Recommended next execution steps

1. Fix and retest the remaining CI failures until Django checks, migration drift and the full SQLite suite all pass. Record exact pass/fail/skip numbers for the exact main SHA.
2. Finish **05 shared customer**: UI/API scope, customer associations, invoices, spend/credit separation, privacy/retention and verified merges. Keep standalone retail experience independent.
3. Finish **06 loyalty**: tenant-approved reward valuation, checkout redemption/return reversal, coupons/tiers/offer precedence, tax/accounting policy and accessible staff flows. Do not assume points equal UGX. Protect double use at transaction/row-lock level.
4. Finish **07 stock intelligence**: traceable sell-through, aging/velocity/runway, supplier lead time, reorder calculations with bounded provenance/limitations, report/UI export and tests.
5. Finish **08 FEFO/batches**: original-lot returns, batch reconciliation/recalls, expiry quarantine, migrations and concurrent movements tests.
6. Finish **09 purchasing**: requests/quotes/POs/GRNs, discrepancies, supplier invoice/payable settlement and credit-note closure with no duplicate accounting or inventory posting.
7. Update all user-facing navigation, empty states and responsive mobile/tablet/desktop views before marking a phase complete. Then produce release certification only after required PostgreSQL/RLS/concurrency, browser, provider/hardware, backup/restore, rollback and direct VPS evidence.

## Files and boundaries

- Main roadmap: `docs/SUITE_IMPLEMENTATION_TODO.md`
- Feature evidence: `docs/CAPABILITY_MATRIX.md`, `docs/LOYALTY_POINTS_POLICY.md`, `docs/OFFLINE_POS_POLICY.md`
- CI: `.github/workflows/quality.yml`
- Release certification: `docs/RELEASE_CERTIFICATION.md`, `tools/release_certificate.py`
- Production commands: `docs/DEPLOYMENT.md` (follow repository-defined paths/services; do not invent them)
- Entry points: `backend/apps/staff/`, `backend/apps/console/`, `backend/apps/customers/`, `backend/apps/inventory/`, `backend/apps/purchasing/`, `backend/apps/pos/`
- Design: Django modular monolith with server-rendered Bootstrap templates; no unnecessary parallel backend.
- Keep source licensing unchanged without owner choice: `docs/COMMERCIAL_SOURCE_POLICY.md`.

## Handback reporting

After each coherent batch: commit to origin main (no force push); record exact SHA, touched workflow, source/test evidence, what remains, and any failed or unavailable certification gate. Commit the phase checklist changes. Do not state a phase is complete just because files or tests were authored.


### 2026-10-16 — F3 reviewed stock counts (software checkpoint)

- Reused the existing count sessions and stock ledger. Storekeepers record physical quantities, skip uncounted items, and submit immutable audit snapshots for a different manager to approve or return with a reason. Posting rejects changed or net-zero-moved stock instead of overwriting intervening sales, receipts or transfers. A separate approval queue is accessible through the inventory UI and API.
- The existing direct completion domain service is now manager-only, with a regression test proving an authorized storekeeper cannot bypass approval. No duplicate stock ledger or new sale/customer/table dependency was introduced.
- Exact prior green source checkpoint: ed449b03359a0a2f2f2a0062c94bad3f46494a46 — https://github.com/birleopold/Bar-Hotel-POS/actions/runs/38956165341 — 592 passed, 5 skipped, 20 subtests; Django checks and migration-drift checks passed. This final permission guard/documentation commit requires its own CI.
- F3, Phase 07 and Phase 08 stay IN PROGRESS: carton/unit conversions, in-transit transfers, original-lot reconciliation, PostgreSQL two-till races, mobile/browser workflows and physical devices remain unverified.
