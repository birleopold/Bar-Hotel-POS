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

## Register shifts business language — 24 October 2026

Corrected the existing `staff/pos_shifts.html` owner in place: a supermarket till uses **Supermarket / Cashier operations**, an independent retailer uses **Retail / Cashier operations**, and hospitality displays the business workspace label instead of exposing internal business keys. The existing retail regression test now covers this distinction and template compilation. Commits `cc108b498d8c6c337360dc4a4ae1c6859f7139a7` and `4c832fabb49d0ad18b6064691b0a3878182b8b47`.

CI run for the preceding `a8d8268` checkpoint was in progress when checked; no passing test or visual result is asserted. No CSS overrides or duplicate templates introduced. P00 remains open until complete audit, current CI and authenticated viewport comparisons are verified.

## P00 fixture coverage for CSS discovery — 24 October 2026

- Made the CSS auditor accept an explicit isolated root and tracked-file inventory while retaining its normal repository invocation. This permits deterministic regression fixtures without altering checkout CSS or creating aliases.
- Added `scripts/test_audit_css_dependencies.py` with isolated coverage for valid Django static references, missing static references, hardcoded missing URLs, and an existing-but-untracked CSS file which must still be reported missing. Use `python -m unittest discover -s scripts -p 'test_audit_css_dependencies.py'` in the repository root.
- Source commits: `373642014486d7fe8395cc52839449d87ba92357` and `7d929329804ca85f792113443d95e1d32a2b2cbc`.
- **Evidence boundary:** The files are committed; test execution in CI and the full live/browser audit are not yet verified. P00 remains open. No product stylesheet or production data was changed.

## P00 CI enforcement — 24 October 2026

Source change `9924b6d85eea7f1a39fd9a44af4965266ea2624b` places the tracked-CSS audit and its isolated regression tests in the **SQLite CI job before Django checks**. On new `main` pushes, CI executes `python -m unittest discover -s scripts -p 'test_audit_css_dependencies.py' -v` and `python scripts/audit_css_dependencies.py > css-dependencies-current.json`. This is a true gate: missing CSS assets produce a nonzero exit code and fail CI, rather than merely recording a document.

The previous workflow did not invoke either audit command, so earlier passing Django checks would not have established CSS integrity. The new workflow is committed; its resulting CI run has not yet completed and **must not be described as passing**. Browser parity, the broad Django regression suite, and P00 closure remain outstanding.

## CSS gate failure diagnosis — 24 October 2026

[Workflow run 40026732037](https://github.com/birleopold/Bar-Hotel-POS/actions/runs/40026732037) **failed** in "Verify tracked CSS dependencies and audit regressions"; the **two isolated auditor tests passed**. The audit's missing-reference exit code stopped the job before Django tests. The PostgreSQL integration job **passed**.

The auditor was scanning `.py` files, including its own fixture test module, where deliberate examples contain nonexistent CSS paths. Those strings are not template or browser assets and should never count as live CSS dependencies. Corrected the auditor's input scope to Git-tracked `.html`, `.css`, and `.js` files; added a regression covering the Python fixture exclusion. Also made the audit print exact missing references to stderr so redirecting JSON to a report does not suppress CI diagnostics.

Commits: `6fd300aa999a74d57bd004fc4e600d9bb59238a2`, `0a699aabf1b7e92d597291f74f2c5763260e881e`, `d6c900ddb73ab74cb5c5b1c82f2dd4712cd5f00a`, `3a464043f528006d6f896ef909ee2c235a63bd7c`.

This is a correction to the **auditor's source classification**, not suppression of true missing browser assets. The revised CI run and full Django suite require fresh confirmation. P00 remains **in progress**; P01 remains unopened.

## Current verified CI checkpoint — 24 October 2026

**Commit:** `b23bd823011f6dd4026668a285ee84704a3db0d9`. [GitHub Actions run 40060576860](https://github.com/birleopold/Bar-Hotel-POS/actions/runs/40060576860) completed with overall **failure**.

- **CSS dependency check: passed**, including all **three** isolated scanner regression tests. The previous false-positive/hidden-error blocker is resolved for this commit's asset graph.
- **Django system/migration checks:** completed before the automated suite. The CI job ultimately failed in **Run automated test suite**.
- **SQLite test suite:** **69 failed, 805 passed, 7 skipped; 1,141 subtests passed**. Failing areas include tenant-branded staff login, dashboard/console text and structure, supermarket management navigation, and other UI contracts. These are not certified away as merely stale: investigate each against actual required functionality and approved visuals.
- **PostgreSQL integration job: passed**, but this is not production RLS or concurrency certification.

P00 asset-integrity subgate is verified **passed for this SHA only**. P00 overall remains **in progress**, and P01 may not be marked started/completed simply from the CSS check. Follow-on work must trace and fix the 69 remaining failures by genuine implementation/behavior contracts, then re-run CI and compare authenticated browser screenshots. No production deployment is implied.

## Tenant-authentication implementation correction — 24 October 2026

Inspected the failing `tests/test_branded_staff_login.py` cases and traced the actual source: `login_brand_for_request` already returns verified tenant identity, accent, configured `background_url`, and `welcome_message`, but the rebuilt staff login/PIN templates ignored the background and the PIN page ignored the welcome copy. Updated the **canonical existing** `login.html`, `terminal.html`, and `fizo-auth-2026.css` to render those existing fields with a readable image overlay. Kept tenant-verified branding lookup, form actions, worker selection and security behavior unchanged. Login title uses `Staff sign in`; terminal title uses `STAFF TERMINAL`; the branded login's eyebrow now identifies its private workspace.

Commits: `23565942de048023c5eb9888d671bc013c36d371`, `5e917e6b9b31aa2f6f78bdadf64559041ce7582c`, `dd4608149f49329f61a6803e0f6a512ad874fefc`. These are direct replacements in existing owners, not duplicate CSS or templates.

Verification boundary: new CI and browser confirmation pending. Historical 69 failing SQLite tests belong to the earlier `b23bd823` CI run, **not** to these commits. P00 still open.

## Canonical owner-navigation accessibility correction — 24 October 2026

Inspected `backend/tests/test_grocery_owner_console_pages.py` after CI exposed the retail owner's missing `aria-label="Store management"`. The management sidebar is now rendered through `console/includes/fizo_sidebar.html` for the Fizo setup area, and its nav had the generic label `Business sections` despite already knowing `grocery_console_shell`. Corrected that **existing sidebar's nav label in place**: retail/supermarket shows **Store management** and other business lines retain **Business sections**, using the same enabled-business condition as the visible title. No alternate sidebar or CSS layer was introduced.

Source commit `2dd6192ae8a13dac02b30f0043902b6c3e5dc690`. Await current CI and authenticated browser confirmation before marking the corresponding route family or P00 completed. The broader 69-failure baseline remains the last completed full-suite result recorded before these changes.

## Dashboard sourced-insight restoration — 24 October 2026

Root cause: the simplified canonical staff dashboard retained tenant/outlet-scoped `staff_dashboard_operations_snapshot`, `staff_dashboard_low_stock_rows`, and `staff_dashboard_sales_snapshot` in view context but omitted the named operational pulse/low-stock sections and direct report link. Fixed `staff/dashboard.html` in place to display these only when scoped data exists; no demo values, new endpoint, or CSS layer. Consolidated conditional render branches to avoid duplicating stock lists and workload panels. Commits: `b132ef04f0033046957f1fd5748bbd7712056afe`, `45c6872927a5167bf9ac062ef8f04c3b1babadf4`.

This correction addresses real user-facing visibility alongside existing dashboard regression assertions. Browser screenshots and post-commit CI are **not yet verified**. P00 remains open until all gates are independently evidenced.

## Dashboard operations single-owner follow-up — 24 October 2026

While reviewing the prior dashboard change, found that the **Operations pulse** heading was accidentally conditional on a simultaneous sales snapshot. The same metrics could render in another unnamed branch, causing inconsistent visibility and duplicate ownership. Removed that alternate metric branch, made **Operations pulse** the single canonical render path whenever a scoped operations snapshot exists, and suppressed the no-data placeholder when operational data is present. This is a correction in `staff/dashboard.html`, not an overlay or second implementation.

Commits: `2d24962eaf9829838cfab6d3976ba2dd67c2923d` and `3f8faa1daecdf9731399a506aac5ba62d14d35ee`. CI and authenticated browser results for these commits remain pending; P00 is not marked completed.

## Dashboard duplication regression — 24 October 2026

Found a second rendering of `staff_dashboard_operations_snapshot` in the lower dashboard work panel after the source-of-truth **Operations pulse** panel was established. Removed that duplicate loop and renamed the empty work panel to **Getting started**, matching its actual behavior instead of implying unresolved attention items. Added a focused template regression assertion verifying exactly one metric loop, the distinct pulse/low-stock sections, the sales-report link, and Django template parsing. Source commits `022900bbf2c6553c81d68b312256f4dc65b283c9` and `d785a43f3541bc685eacc1595f2c3f9b6ca24c9b`. Latest CI status and full browser review are pending for these changes; P00 remains open.

## Owner management action restoration — 24 October 2026

The redesigned dashboard had a restricted `show_workspace_admin_tools` section but removed the direct authorized owner pathways to **Open admin console**, **Team & onboarding**, and **Add staff member**. Updated only the existing `staff/dashboard.html` management section, preserving the permission guard and existing named routes; no duplicate page, CSS override, or bypass of tenant authorization. Added source-level regression checks of route resolution, permission guard, and template parsing in the existing retail template test module.

Source commits `03c3a381b0c599325d7de400449a3b089c21e0b7`, `1c2669779de84dae82f44cdea3c8d5a57a7ac643`. CI and authenticated browser acceptance for this revision are not yet verified. P00 stays open.

## Hospitality administration accessibility — 24 October 2026

Corrected the canonical Fizo console sidebar's accessible navigation name: store-only management uses `aria-label="Store management"`, while hospitality and other non-store businesses use `aria-label="Administration navigation"`. Preserved the existing sidebar, visibility checks, and links without adding CSS or an alternate layout. Strengthened the existing business-line isolation regression to require the appropriate hospitality label and explicitly reject supermarket navigation language. Source commits `a5ba5a37605323dadb66ec745385235247cc3829` and `f76f6a5c306f8deb2ff1af2b7b733a7caf9134d5`.

Current CI and live browser verification are not yet complete for these commits. P00 stays open; P01 does not start on an unverified baseline.

## Hotel reservations filtered empty-state correction — 24 October 2026

Fixed the canonical `staff/lodging/reservations_list.html` front-desk empty state. Previously a filtered reception queue with no matching stays displayed the generic "No reservations in this view", which did not explain that a filter was hiding records. It now displays **No stays match this task** when a lane or status filter is selected and **No reservations yet** on a genuinely empty unfiltered register, with context-appropriate guidance. Existing permission-protected create action and branch scoping are unchanged. Added a template regression and compile check in `test_fizo_hotel_reservations_layout.py`.

Commits `e9ad889d0c08e47fbacad858690b85037dd71728` and `6f5a6a8709240502896917b125ee55ccffd35333`. No CSS or additional templates; CI and real browser validation are pending. P00 remains open.

## Dashboard business-line introduction — 24 October 2026

Corrected a shared generic dashboard introduction in the existing `staff/dashboard.html`: retail/supermarket now says **Here's your store at a glance**, hotel shows **Guest accounts, reservations and room readiness at a glance**, and a user without a selected membership sees **No workspace selected** with the existing selection form. This is conditional presentation, not a new dashboard or CSS override. Added template assertions for the three cases. Source commits `2d3631c8fa8a86a75fb579f3d75a3b7db5d1d414` and `49000b7514e4f448165f4bfbf861e67da79cc33e`. CI and authenticated browser verification remain pending. P00 remains in progress.

## Dashboard empty-state accuracy — 24 October 2026

Corrected the existing staff dashboard's lower panel: it previously showed "Nothing requiring attention is available yet" regardless of whether the panel was meant for **Popular items** or **Getting started**. It now distinguishes a reporting period with no sales from a user who can begin via their existing quick actions. Added a template-parsing regression test guarding both states. Only the canonical dashboard template and existing test owner changed; no CSS or duplicate views were introduced.

Source commits: `f18cbe4d2813d4881c45f12a1bf4fd0a87afe7d4`, `6021c4eb66797cdcf95d8be8e4d6f6b3c7e9c8b2`. CI and authenticated viewport validation for these changes remain pending. P00 remains open.

## Populated-items dashboard heading — 24 October 2026

The canonical dashboard labeled its work panel **Popular items** whenever a sales snapshot object existed, even if it had no ranked item rows. Corrected the heading to require real `top_items`; otherwise the sales panel is **Sales activity**, matching its no-sales empty state. Added a focused existing-suite template regression. Commits `3553006570cc66e7e54c9c314b4b8a9abc6a044f` and `0202fb1630c2a4deb529eba7521f55d70d491d98`. No new CSS or template; new CI and browser acceptance are pending. P00 stays open.

## Missing workspace versus unselected workspace — 24 October 2026

Adjusted the existing staff dashboard so an account with available memberships but no selected workspace receives the selection prompt, while an account with **no memberships at all** receives **No workspace available** and an administrator-assignment explanation. No permissions, tenant data, or authorization path changed. Added a template regression protecting the distinction and retained the existing required tenant selection form. Commits `5c20cb78c344c402f838da1f0c614d746e028083` and `1765f1e2500dca2f5fa33907cb8dc8240cc01df7`. CI and authenticated browser acceptance for these commits remain unverified. P00 remains open.

## Sales ranking accuracy — 24 October 2026

The dashboard previously claimed **no sales were recorded** whenever the sales snapshot existed but its `top_items` list was empty. An empty ranking does not prove zero sales, payments, or revenue. Corrected the canonical empty-state language to **No ranked products to show for this period**, with a link to the existing sales report, and strengthened its template regression. This avoids a misleading financial claim while retaining all live data and authorization constraints. Commits `6f2376cf5eac01641f2de8f5f08192b781e0b2b8`, `855ba64c114e29cb72b8292d8c3efe936398a3c0`. CI and browser acceptance for this SHA are pending. P00 remains open.

## Hotel launch terminology — 24 October 2026

Fixed the shared dashboard quick-start heading for the lodging business line. It previously invited a hotel worker to start the next **order** whenever an ordering entitlement was present, conflating guest operations with restaurant sales. Hotel staff now see **Ready for the next guest?**, while bar/lounges retain tab language and supermarket/retail remain checkout-specific. This modifies existing conditional copy only, preserving permissions and links. Added a template regression test. Commits `d4c734ccf1f0b3b6d2dd4201e06341cd35ba3463`, `9ffa19b3d7e2d9891dba6e99d19450c0d21e12ad`. CI and browser acceptance pending; P00 remains open.
