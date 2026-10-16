# Codex handoff — 16 October 2026 (Africa/Kampala)

## Quick start

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
