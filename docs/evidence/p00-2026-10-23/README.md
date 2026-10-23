# P00 discovery checkpoint — 23 October 2026

Authority: [complete implementation roadmap](../../FIZO_COMPLETE_IMPLEMENTATION_ROADMAP_2026-10-23.md).
Source baseline: `8d45fb35bff514691b5650cdcc66f4e65c0902d5` on `main`.
Status: **in progress**, not phase completion. No new phase or product scope added.

## Fresh evidence

- [Baseline CI run](https://github.com/birleopold/Bar-Hotel-POS/actions/runs/40019088903): SQLite suite **83 failed, 801 passed, 7 skipped**, 1127 subtests passed. Django system and migration checks passed. PostgreSQL integration job passed; this is not restricted-role RLS or production certification.
- Existing route inventory now limits templates to Git-tracked files (avoids counting virtualenv templates) and emits literal template inheritance/include and CSS/JS links.
- Resolved inventory: **636 URL patterns**, including 281 generated admin, 188 API/data, 8 action/service and 159 visual candidates. **156 tracked templates**, with **28 visual candidates needing dynamic view/template tracing**.
- CSS dependency audit **fails** on eight links to missing files. Original results are preserved in `css-dependencies.json`. No files deleted or duplicate compatibility stylesheets created to conceal the failures.
- Local Django system check and migration-drift check passed after the inventory change. The full-suite count above is exact-baseline GitHub CI evidence, not a new local full-suite result for this documentation/inventory checkpoint.

| Broken asset | Consumers |
|---|---|
| `staff/hospitality-workflow.css` | KDS queue, orders list, shifts, table form |
| `staff/staff-theme.css` | Login, terminal, public signup |
| `staff/fizo-retail-sales.css` | Orders list |

The generated route business classification is a keyword-based discovery aid, **not an authorization or entitlement result**. Literal asset edges include conditional branches, not proof that every edge loads in every business. Dynamic templates, backend service/model writes, inherited cascade, middleware/permission enforcement and browser states require manual trace.

## Reproduction

Use the repository virtualenv and `DJANGO_SETTINGS_MODULE=config.settings.development`, `DATABASE_URL=sqlite:///:memory:`. From this directory run `../../../scripts/inventory_fizo_routes.py`; from repository root run `scripts/audit_css_dependencies.py` and capture its JSON. Both are read-only with respect to business data. CSS audit exit code 1 is an expected recorded failure at this baseline.

## Reference and acceptance boundaries

Four images supplied in this chat are already tracked in `docs/design/references/`: `industries.png`, `retail-dense.png`, `retail-comfortable.png`, `touch-pos.png`. The roadmap mentions five uploads; the fifth management image is not present in this chat's four attachments. Do not invent that baseline or claim its pixel acceptance.

No screenshots, browser comparison, production deployment, hardware, backup/restore or owner visual acceptance were collected in this discovery checkpoint. P00 stays open. Next work: trace the eight missing dependencies to canonical owners, categorize actual failing assertions from the exact CI run, and collect the five required viewport baselines before CSS replacement.

No migrations, financial writes, stock mutations, API changes or live service changes are included.

## Follow-on P00 source correction (after desktop commit `e6a3b3e`)

- Replaced hard-coded `/static/staff/fizo-auth-2026.css` in staff login and PIN-terminal templates with Django `{% static 'staff/fizo-auth-2026.css' %}`. This changes asset resolution only; it does not introduce new CSS, styling patches or alternate view controllers.
- Enhanced `scripts/audit_css_dependencies.py` to include hard-coded `/static/staff/*.css` links alongside existing Django static tags and relative stylesheet imports. This catches a class of references previously outside the audit.
- Verified the three changed files were persisted to `main` by fetching their contents back from GitHub.
- This checkpoint **does not** assert a completed source inventory, resolved eight-reference baseline, browser pixel match, passing full suite, live deployment or P00 completion. Re-run the audit and capture fresh CI/browser evidence at the next verification gate; the earlier 83-failure snapshot cannot be treated as current test results.

## Continuation: stylesheet ownership evidence — 23 October 2026

At commit `e212ed37b03ef89b33737b8f60f8a09a1e6e530a`, the CSS dependency scanner now also:

- Records hardcoded CSS URL consumers separately from Django `static` template tags.
- Records relative `@import` file-to-file ownership edges, not merely missing imports.
- Reports CSS files with no *literal* consumers as candidates requiring manual tracing; this is **not** proof those files are unused and is not authorization to delete them.

The historical `css-dependencies.json` remains baseline evidence rather than a current report. Current broken-reference totals and P00 certification still require execution of the updated script, Django source/runtime trace, live browser screenshots, and CI verification. No stylesheet was removed or replaced in this checkpoint.

## Current source trace: historical eight CSS errors and business-line leakage

At the `e22f14e9ac457c6563a63fba9298175a8fd5502a` checkpoint, the seven template files associated with the historical eight missing CSS links were fetched again from `main`:

- `kds/queue.html` now imports `staff-kds-operations.css` and `management-workflows.css`; it no longer names the missing singular `hospitality-workflow.css`.
- `orders_list.html` selects existing `retail-workflows.css` or `management-workflows.css` by sales mode; it no longer names `fizo-retail-sales.css` or `hospitality-workflow.css`.
- `pos_shifts.html` uses `management-workflows.css` and `fizo-register.css`; no singular missing file. Its register eyebrow now uses retail-specific wording only for retail, or a business-specific register title for hospitality; no longer labels a hotel/bar register “Fizo / Supermarket”.
- `table_form.html` imports existing `management-workflows.css`, not the missing singular hospitality filename.
- `login.html` and `terminal.html` import existing `fizo-auth-2026.css`, not `staff-theme.css`.
- `backend/templates/public/signup.html` imports `fizo-fresh.css`, not `staff-theme.css`.

This is a **source check of the historical eight references**, not a fresh full 156-template CSS audit. The historical JSON remains unchanged for provenance. P00 stays **in progress** pending the complete audit execution, 636-route dynamic trace, full test suite, browser screenshots, and responsive/tenant acceptance. No style or controller aliases were added.

## Continuation: tracked-file dependency audit and CI triage

The CSS auditor now checks stylesheet targets against the **Git-tracked file set**, not merely against files present on the developer's disk. This prevents an uncommitted local stylesheet from disguising an asset that would be missing after deployment. Report ordering is deterministic and duplicate consumer entries are removed. Commit: `45244f2c3990e63fbe27835274a560d2122d4b6c`.

The latest *completed* CI result inspected during this continuation was [run 40023051901](https://github.com/birleopold/Bar-Hotel-POS/actions/runs/40023051901) at `fd4c976`: **71 failed, 801 passed, 7 skipped** in SQLite checks; the PostgreSQL integration job passed. This is newer than the original P00 83-failure baseline and demonstrates that P00 must remain open. Several failures assert superseded literal CSS filenames, markup text, or selector arrangements. **Do not add deleted aliases or change tests just to hide failures**: for each failure, establish the intended current user-facing behavior and correct either the implementation or its meaningful behavioral test.

The CI run triggered by `45244f2` was still in progress when inspected; it is not represented here as passing. No fresh browser or hardware verification is claimed.

## CI contract cleanup — 24 October 2026

Following actual failing GitHub Actions assertion output, two *source-level test contracts* were updated to match the canonical implementations already in `main`:

- `backend/apps/staff/test_fizo_cashier_support_layout.py` now asserts the live two-panel cashier grid and basket width instead of demanding a removed `!important` one-column override. This protects the approved basket/product split from regression.
- `backend/apps/staff/test_fizo_retail_sales_layout.py` now requires the existing `retail-workflows.css` and explicitly rejects the removed `fizo-retail-sales.css` filename. No CSS aliases were recreated.

Commits: `fc4e8b5879666de2c1909bf7025d1f451eb7ed6b`, `48b704c5817b05fe05859296a4cdd95a6c46dc2f`.

These edits correct stale layout assertions, not financial or operational behavior. Test pass status and browser pixel parity are **not yet verified** for these commits; track new GitHub Actions results before changing P00 status. The broader failing suite still needs root-cause triage. No stage or production certification is claimed.

## Business-line language correction checkpoint — 24 October 2026

- The canonical retail sales landing template now displays **Retail / Cashier** for an independent `retail` business and **Supermarket / Cashier** for supermarket use, including its accessible page label. Previously it showed supermarket wording unconditionally, exposing a different business line.
- Extended the existing retail sales layout regression test to guard this distinction and reject the legacy universal “Fizo / Supermarket / Cashier” heading. No stylesheet, overlay or duplicate template was added.
- Commits: `caeaa72882a9edfcc98741cb4f7ca7e89e98eb35` and `40c252354fb7383ffcfb1dd6160d801aa9035be0`.
- **Verification:** source edit committed; fresh tests, live tenant rendering and screenshot acceptance are pending. P00 remains in progress.

## Standalone retail dashboard correction — 24 October 2026

- Corrected the existing `staff/dashboard.html` heading logic: independent retail now renders **Retail dashboard**; supermarkets retain **Supermarket dashboard**. Previously both variants rendered **Supermarket dashboard** despite distinct business entitlements.
- Added a corresponding regression test in the existing retail layout test module; it verifies both branch-specific headings and compiles the Django template.
- Source commits: `969cb32113aa2af6b267a0c29d16a429868e956a`, `ea97fe74e43e66cb8f8183ec1cb78fc6aebf9267`.
- No new CSS, replacement patches, extra templates, schema changes, payments or stock operations. Real tenant rendering, visual acceptance and CI passing status **not yet verified**. P00 remains open.
