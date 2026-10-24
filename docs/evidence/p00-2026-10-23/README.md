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

## Hotel dashboard primary workflow — 24 October 2026

Corrected a real navigation priority problem: when a lodging tenant had both POS/orders permission and lodging permission, the shared dashboard's first-match branch opened POS and hid **Front desk**. The canonical dashboard now prioritizes **Open reservations** for the lodging business line whenever the role has lodging access; hotel workers can still access POS through existing authorized navigation. No new route, CSS or template. Added source-level regression checking hotel branch precedence and template compilation. Commits `d74b90343b081bddd18d4c69640d6fe8a4fb1666`, `c7b2921f60d22ae7ebe645b6f39a2230547fe9fc`. New CI and authenticated browser acceptance pending. P00 is open.

## Hotel dual-role front desk plus POS — 24 October 2026

Followed through on the primary hotel navigation correction: previously a hotel worker with both lodging and POS access could open reservations from the dashboard, but the primary launch replaced their visible POS shortcut. The existing lodging launch now presents **Open reservations** as the main action and **Open POS** as a secondary action **only when `staff_nav.orders` is true**. Reuses the existing authorized `staff-orders` route and canonical template without adding CSS or a competing screen. Added a regression verifying the conditional link. Source commits `f2fb62be78e4dfc3e38546ee20f0b3969f17a350`, `0d306df6a141220b7c3267495212a8de24734526`. CI/browser acceptance remains pending; P00 remains open.

## Hotel front desk entitlement precedence — 24 October 2026

Removed an unnecessary additional `staff_show_lodging_nav` gate from the hotel dashboard's primary Front desk launch. The canonical launch now checks the lodging business line plus the effective `staff_nav.lodging` permission directly; previously a false display flag could divert a lodging-authorized hotel worker to POS. Optional POS remains conditional on `staff_nav.orders`. Updated the source regression accordingly. Commits `dda3f68958bcbfa6588136626b65d0c590accd0e`, `e23b0f04531bb08f8dd5d44499a5b3b8c518c140`. CI and authenticated browser verification pending; P00 remains open.

## Cross-phase hotel property-pulse implementation — 24 October 2026

User-approved rule: for each feature corrected during P00, implement directly related work in the future phases together rather than deferring connected items. This is recorded in the master roadmap at commit `f7d19109042ed4ba8a76247907a32fb5f21ed838` without prematurely accepting any phase.

**Related phases:** P00 verification; P02 understandable headings and drilldowns; P03 tenant/site-scoped output and existing permissions; P12 hotel arrivals, room readiness, housekeeping/maintenance; P13 dual hotel/POS navigation; P15 source and browser QA. The existing `dashboard_lodging_snapshot` service already supplies live tenant/site-scoped `site_name`, arrival rows, room statuses, maintenance counts and authorized view URLs. The redesigned dashboard hid the named **Property pulse** and selected property context, even though the underlying service and guest records were present. Restored **Property pulse**, **Today at [selected property]**, and direct housekeeping/maintenance drilldowns within the canonical dashboard without extra queries or mock data. Kept existing arrival and room panels. Added source-level regression for these fields and template parsing.

**Changed sources:** `backend/apps/staff/templates/staff/dashboard.html` (`12176d82c570f02d83cf51cc3c04734af82f9e8d`) and `backend/apps/staff/test_fizo_retail_sales_layout.py` (`70c208794f0af923946b78b2821dcf647d7ca02e`). No new CSS, migrations, URL routes or controllers. The preceding completed CI run `40063750572` at `fd5767ac` had **51 failures, 826 passed, 7 skipped**; PostgreSQL integration passed. CI and authenticated screen comparisons for these new commits remain **pending**. P00 and P12/P13/P15 acceptance gates remain open.

## Cross-phase hotel rendered integration regression — 24 October 2026

Extended `backend/tests/test_folio_settlement.py::test_dashboard_property_pulse_uses_scoped_live_lodging_counts` to check the **actual rendered authenticated response**, not just the template source. It now asserts the tenant/site label, real arrival guest, housekeeping and maintenance destination URLs, live maintenance zero count and dirty room count. This regression spans P03 tenant/site scope, P12 live hotel service, P13 hotel dashboard navigation and P15 rendering evidence, all as one connected feature package. Source commit `70d0e5d39b4d113a730f61b02d4c373a28f8a760`. No production code or CSS change was needed for the test itself. Latest CI execution of this test and viewport/pixel checks remain pending, so P00/P12/P13/P15 are **not** complete.

## Cross-phase hotel no-arrivals empty state — 24 October 2026

Completed a connected P02/P03/P12/P13 dashboard correction while P00 verification continues. When the live property snapshot has no arrival rows, the existing **Today's arrivals** panel now explicitly states **No arrivals scheduled for today at [selected property]** instead of silently showing only generic Quick access links. Existing role-gated Orders/Items/Stock/Reservations links remain available. The selected property name comes from the same membership- and site-scoped service; no new queries, fake values, CSS or routes. Source commits `c3dfe6034e67c779f2fc1bb24fc761c1713e45a8`, `7755d822cbc2c057e8187cf13019e216747e2a12` include a regression test for the canonical template. Post-commit CI and authenticated browser comparisons pending; no phase marked complete.

## Cross-phase inventory CSV recovery — 24 October 2026

Resolved a real failed-import recovery defect spanning P02 (visible action), P03 (session-bound access), P08 (inventory movements), P09 (staff action), and P15 (rendered integration regression). The existing `StaffStockMovementListView` supplied `has_upload_error_report` based on its current session but the canonical `inventory/movements.html` template did not present the download. The ledger now renders **Download last error report** only when an error report is available, linked to the existing download URL. Strengthened `StaffInventoryCsvUploadTests::test_ledger_shows_download_last_error_report_button_after_failed_upload` to assert both the actual route and flag. Existing error download authorization and CSV import behavior remain unchanged. No new CSS, routes, JS, migrations or duplicate templates. Source commits `70a33f6f9b4bc1f9764d06f0f46a7a8260086af8`, `7f280e9d4d45982f2a20a6c32a98903daddd9143`. Post-commit CI and browser acceptance pending; phase gates still open.

## Cross-phase stock-transfer posting disclosure — 24 October 2026

The stock-transfer form's description was vague about when inventory is deducted. Updated the canonical dispatch form to state explicitly that **only the sender's stock decreases now** and **the receiving outlet's stock is added after recipient quantity confirmation**; the existing two-stage transfer implementation, anti-double-submit guard and accessible live status are unchanged. Strengthened the existing guard regression so both dispatch and receipt expectations remain visible. Related P02 form clarity, P03 outlet-scoped operation, P08 transfers, P09 staff handling and P15 tests. Commits `804f5999f5e5594a7aeea5dc3bdead10ff97c7c2` and `de4bb32b330e26a4f1d2076894ce75f0208c82b2`. CI/browser acceptance pending; no phase marked complete.

## Cross-phase product photo upload — 24 October 2026

**Customer-discovered production gap:** POS product cards and staff catalogue showed image tiles, but the product create/edit form had no image upload and did not even expose the existing `display_image_url`. Addressed this as one P00/P02/P03/P05/P06/P08/P13/P15 package rather than postponing a second image system.

- Added nullable/optional `MenuItem.product_image` with database migration `catalog/0012_menuitem_product_image.py`, a reusable `product_image_src` selector favoring uploaded images and falling back to the existing URL, and Pillow image decoding dependency.
- The existing tenant-admin `ConsoleMenuItemForm` now accepts and validates JPEG/PNG/WebP images up to **5 MB**; it also exposes the optional external URL as a fallback. The existing editor has `enctype="multipart/form-data"`, current photo and the standard clear-file widget. Existing create/update permissions, tenant category querysets, and save synchronization are retained; no new endpoint.
- Cashier product tiles (`staff/includes/fizo_pos_catalogue.html`) and staff catalogue rows (`staff/menu_list.html`) use the same `product_image_src` source. Existing URL-only products are preserved.
- Configured Django `MEDIA_URL=/media/` and configurable `MEDIA_ROOT`; deployment Nginx example serves a **public product-image directory** independently of static files. Production must provision `/var/www/leosoft-pos/media/`, write access for the application, and set `MEDIA_ROOT=/var/www/leosoft-pos/media` before uploads are usable; do **not** deploy without persistent media storage and web-server review. Nginx example was updated, not applied automatically.
- Extended source contract checks and added an authenticated owner POST test generating a valid PNG, storing it in an isolated temporary media directory and verifying its persisted path and display URL.
- No existing CSS duplication or new visual page; no other product data migrations beyond the optional image field.

**Verification:** CI/migration check and real desktop/tablet/mobile browser acceptance of upload/display are pending. End-to-end media serving and permissions must be verified on VPS. The affected workstreams are partially implemented and remain open until those gates pass.

## Cross-device optional product images — 24 October 2026

Expanded the catalogue image package across P02 (desktop/mobile experience), P03 (tenant/role permissions), P05/P08 (catalogue management), P06 (cashier product photos), P13 (all enabled business lines) and P15 (integration checks). A worker may now create a product or import it from CSV **without a photo**, then choose **Add photo** from the canonical catalogue row. For saved products, the desktop editor presents **Copy phone link** and a **Phone photo upload** link. Open the link on a phone, authenticate as an authorized owner/tenant administrator with the same business workspace selected, and take/select a photo using its native file picker. The standalone mobile POST updates **only** the product photo, preserving unsaved descriptive/price fields being edited simultaneously on desktop. The desktop editor checks the same authorized product-photo endpoint every eight seconds while visible and replaces its photo preview on a new upload, without reloading or discarding form data. Photos remain optional for all products and CSV imports; existing external URLs remain fallback.

**Security/design boundaries:** all reads/writes use the existing organization-admin mixin, tenant-scoped product lookup and CSRF-protected POST; the status response is no-store. No public bearer-token upload links or cross-tenant asset references. The phone must be signed into the selected tenant; copying the URL does not grant access. A new unsaved product must first be saved so its own scoped image target exists. Direct computer upload stays available in the existing editor. No added CSS overrides or extra product-creation form; the small phone photo view is a task-specific authorized screen.

**Tests:** authenticated phone-photo POST verifying image persistence, unchanged SKU/price and JSON status, and cross-tenant GET/POST returning 404 added to existing console tests. New CI execution and real device browser acceptance are still pending. Deployment still requires persistent MEDIA_ROOT and /media/ serving as separately documented. Do not mark any phase complete without this verification.

## Desktop photo synchronization correctness — 24 October 2026

Fixed a cross-device state synchronization bug: the desktop product editor compared only `product_image.name` against the phone status response. Products using the supported external URL fallback could change photos without changing that key, so the desktop preview would remain stale. It now compares the effective `product_image_src` with the returned `image_url`, updating the preview for both uploaded and URL-based images. Retains authenticated same-origin, no-store polling and optional no-photo state. Added source regression. Commits `b38d2b7016cfe4b4489fbf24007a578e958741dc`, `93a82dd71c3726c06fd9fefa9da55c5f4380cc4f`. CI/browser verification pending.

## Phone upload synchronization recovery — 24 October 2026

Followed through on P02/P08/P15 cross-device product photo workflow. The desktop editor previously polled the photo status every eight seconds but silently swallowed errors; after a login/session expiry or connectivity issue, an operator had no way to diagnose or retry other than reloading a potentially unsaved product form. It now includes **Check for photo** (non-submitting manual refresh), and gives a visible sign-in/retry explanation when the authenticated status check fails. The existing periodic check and no-page-refresh edit state remain intact. Added a source-level template test. Commits `cb94ef69742c7b732b0566b389f87af214f7d895`, `d8ed2d22be6b9963f4712c76b9d5de0de96f3204`. Automated and real-browser acceptance pending. No new CSS, tables, media handlers or redirects.

## Phone-based optional product photo removal — 24 October 2026

Extended the connected P02/P08/P15 product photo workflow so a staff member can remove an uploaded photo on the same authenticated mobile photo page used to capture it. The POST action is scoped to the tenant's existing product editor permission, uses CSRF protection, clears only the model image reference, and leaves the product, stock and pricing untouched. The action is visible only when an uploaded image exists; an external image URL remains a fallback when configured. The old stored file is not automatically deleted, avoiding destructive concurrent storage operations; retention/cleanup remains a separate policy decision. Added a source-level regression. Source commits `9f5b818b1858f37b309628a6eed82a265b1b5499`, `9f69c893a218198f50c34c263a14894beb59f5ea`, `02d30b13fcb61d4978466c9838a31f717653ec85`. CI/browser acceptance pending.

## Connected product editor concurrency guard — 24 October 2026

Resumed P00 baseline and the directly related P03/P08/P15 catalogue work. The existing desktop product save built its image field from an earlier form instance and could overwrite a newly saved phone image while both people were editing the product. Updated the canonical `_save_catalog_item_safely` transaction to refresh the **latest tenant-scoped product image under row lock** when the desktop request **did not explicitly edit the image**. Explicit replace/clear remains allowed through `form.changed_data`. Added a source contract regression. Commits `de6e511538212d01466499e978a4a2d96bb54dd0` and `528ad8b44c64bbfd28acd6dfbf2a9a3302ef602a`. A deterministic concurrent integration test, full CI, and browser/VPS acceptance are still required; no phase is marked complete.

## Product phone-to-desktop save integration regression — 24 October 2026

Added a database-backed owner integration test to the existing console suite, covering the entire sequence: open desktop editor, upload photo through the phone-only route, submit the earlier desktop form without touching the image field, and verify the updated product name and unchanged persisted image filename/file. This guards the P03/P08/P15 cross-phase source fix from `de6e511538212d01466499e978a4a2d96bb54dd0`, rather than relying only on source-string tests. New test commit `396535844c1aff74275042b339c47ac023324d42`. CI execution and true parallel browser testing are still pending; phase gates remain open.

## Cross-business inventory branding — 24 October 2026

Continued the approved P00/P03/P08/P13/P15 cross-phase roadmap. The shared stock movement ledger and CSV import screen incorrectly hardcoded **Fizo / Supermarket / Inventory** for all businesses, including bars, restaurants and mixed tenants. Both canonical templates now render the selected `staff_product.workspace_label` rather than another business line's name. Existing inventory permissions, import error download, form submission and CSS owners remain unchanged. A source regression asserts both pages use the current workspace label and the hardcoded supermarket branding is absent. Commits `fb8eb201c4dc47c6672ce619f5bd1d03452e73ac`, `637fe26adfea0c15e812f01c3f5cefcb8b8ee7e0`, `d901ad923cabc8b54f0ec44b4180afcb5becaeb4`. CI/browser comparison pending, phase gates remain open.

## Entire inventory business-context label sweep — 24 October 2026

Followed the P00/P03/P08/P13/P15 cross-phase rule rather than fixing individual screens repeatedly. After the earlier movement ledger/CSV-import correction, inspected all stock templates and fixed six more hardcoded **Fizo / Supermarket / Inventory** headings on balances, batches, intelligence, movement form, scale labels, and shelves. All eight affected screens now derive their inventory breadcrumb from `staff_product.workspace_label`, with no new routes, CSS, database mutations or authorization changes. Extended the existing inventory template test to cover all eight pages and reject hardcoded supermarket naming. Final code/test commit `3183482be6817716d720496179fe457d20a9de4e` following six template commits. CI and real-browser acceptance are pending; no phase is marked complete.

## Server-side supermarket quick-basket idempotency — 24 October 2026

Closed the source-level duplicate-submit gap following client-side disabled buttons. Every staff sales landing page now supplies a server-generated UUID request key; **new sale** and **hold basket** get different keys. Added optional `Order.quick_create_key` with migration `pos/0029_order_quick_create_key.py` and a tenant-scoped database unique constraint. The quick-create POST serializes requests for the tenant, looks up an existing order by key and redirects a same-user, same-outlet retry to the original basket instead of creating another. Mismatched user/outlet replays and malformed tokens are rejected; older tokenless integrations retain their existing behavior. PostgreSQL row locking supplies concurrency serialization, while the unique constraint is the final integrity barrier. Added database-backed tests for duplicate retry, independent hold creation and malformed-key rejection. Cross-phase P00/P03/P05/P06/P09/P15 implementation; **migration, CI and authenticated browser verification remain pending**. No acceptance phase was closed.

## P01 CSS ownership consolidation: inventory stock balances — 24 October 2026

Merged the full 3,082-byte `fizo-stock.css` rule body into the existing `fizo-inventory-workflows.css` inventory owner, preserving selectors and source order, then switched the canonical stock balances template to load that owner. Added a source regression validating the page reference, selector retention and template compilation. The old file is **retained temporarily** until all template/import/test references are exhaustively verified; this is consolidation in progress, not evidence of complete deletion or browser pixel parity. Source commits `8589bd5b6a19dcfa6b77ab034131610296fbcaf7`, `422494256fc41b0b48ea33dc3da8117f2693a3aa`, `9b55c2236cddb9bee4d800f43705805dcf49545a`. CI and responsive visual comparison pending.

## P01 retired stock stylesheet — 24 October 2026

After migrating `inventory/balances.html` to canonical `fizo-inventory-workflows.css` and copying the complete former rule block, deleted the superseded tracked `backend/apps/staff/static/staff/fizo-stock.css`. The inventory stylesheet retains all former `.fizo-stock` rules. Updated the regression to assert both correct template inclusion and physical removal. GitHub code search found no other indexed references, though full rendered browser/CI checks are outstanding. Deletion commit `3084a08f486c954ec58b702a8af943b1cf835bbf`, test commit `84f6b558a71306cb770f3c6bc8b1785cc73ff872`. This is one completed file-level consolidation, **not** completion of P01 or visual parity.

## P01 CSS consolidation: purchasing and suppliers — 24 October 2026

Moved the complete preexisting `fizo-purchasing.css` rule block (2,919 bytes) unchanged into shared `management-workflows.css`; switched all six purchase/supplier screen templates (`purchase_order_create`, `purchase_order_detail`, `purchase_orders_list`, `supplier_balances`, `supplier_form`, `suppliers_list`) to that owner; updated the dedicated six-page source regression; then **deleted** the legacy `fizo-purchasing.css`. No new overlay, selectors or layout assumptions were introduced; historic responsive appearance still requires authenticated desktop/tablet/mobile browser comparison. Source merge `07b7846f835def04322f5dd48f29c495bcd5c717`, test `1068339aa4dacb74821bfd7ea3701a3efd1112aa`, removal `1679fa12537756d2abfa095978f72818629368e6`. Last completed baseline CI preceding this change: SQLite **50 failed, 847 passed, 7 skipped**, PostgreSQL integration passed. P01 and P00 remain open.

## P01 guided setup stylesheet consolidation — 24 October 2026

Verified `console/context_processors.py` sets `fizo_setup_area` for `/console/org/` routes and `console/base.html` loads `fizo-setup-area.css` under that context. Merged the complete 8,632-byte guided setup rule body, unchanged, into the canonical `fizo-setup-area.css`; removed the separate stylesheet include from `console/org/setup_wizard.html`; deleted the superseded `fizo-setup-wizard.css`. Added a compilation/reference regression checking the context, inherited stylesheet, original wizard selectors and physical deletion. Merge `0c4c57c0f0681fcb0c06bbcd769b92cc07aeaf23`, template `33037e671dd8841f6129c248eb55d9d356aa12c2`, deletion `6d91c66fd3984abf871a91c3df94f8be2773272b`, test `ae5586cc73384d5daba108e6a6bee50261c19837`. CI and visual parity pending; P00/P01 remain open.

## Shared tenant branding corrections — 24 October 2026

Confirmed **Fizo is a testing tenant, not the software/product brand**. Removed hard-coded visible Fizo labels from the shared org console nav and sidebar and all eight inventory screen headers, replacing them with `console_active_tenant.name` or `request.tenant.name` with neutral fallbacks. The internal `fizo-` CSS class/file prefixes remain implementation identifiers, not user-facing tenant labels, until a separately validated refactor; no global rename risking broken selectors. Added source regressions to block Fizo branding regressions. Includes source commits `faf0b8f35fe6f3de77292c52badde3ac076198ed` through `7f5bf70755aed690f8f9a17d52bba5fb330c5e55`, test `f05675d61148580c99ce6e20b68bca8ffd2f38cb`. Other templates and real cross-tenant browser verification remain on P03/P15 acceptance gates.

## Shared purchasing and organization tenant name — 24 October 2026

Removed the hard-coded visible `Fizo / Supermarket / Purchasing` eyebrow from all six shared purchasing/supplier templates, replacing it with the actual `request.tenant.name` plus neutral fallback and generic Purchasing context. Removed `Fizo / Business management` from the organization overview. Added source regressions for all seven pages. No data access isolation is claimed from label changes alone; authenticated two-tenant runtime verification and unrelated existing CI failures remain open. Source `e651ea66d20075d13c28fa04bad521a4b0932a61` through `1862d6d2855cbc86aa80effa2d12c17e21ef59dd`; tests `78e2af3f80c4f9655b9c66a6d6adc4e41d6dceaf`, `35fd6cd0fb7f430d9a8fbd068a05659230b690df`.

## Tenant-specific dashboard and stock operations headings — 24 October 2026

Removed the Fizo test-tenant label from the shared staff dashboard (browser title, accessible landmark label, and page heading), three stock-count screens and two transfer screens. These now display `request.tenant.name` with neutral fallback, retaining existing internal CSS classes. Added source/template regression coverage in `apps/staff/test_fizo_inventory_workflows.py`. Latest test commit `d000a829dfdb29eb82644d25bb5b1638976aed12`; authenticated multi-tenant browser and CI acceptance remain open.

## CSS import dependency-audit coverage — 24 October 2026

The tracked-file P00 CSS auditor now recognizes quoted imports, unquoted `@import url(file.css)`, and imports with query suffixes. Added isolated fixture coverage including an external URL (which must not be reported as a missing local file) and a valid imported file (which must appear in its consumer graph). Source commit `868b4373`; fixture commit `b4a7d64d`.

An isolated regex smoke check recognized all four fixture import styles. The full audit and exact-commit CI are **not yet recorded as passing**. This is a dependency-discovery improvement only; it does not authorize deletion of candidate stylesheets or advance P00/P01 acceptance. Keep browser, source-level consumer tracing, tenant scoping and the approved viewport checks open.
