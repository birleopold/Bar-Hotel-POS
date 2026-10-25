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

## 24 October P00–P04 implementation: CSS graph and real PIN timeout mismatch

- The canonical P00 CSS audit now produces literal template `extends`/`include` edges, dynamic/unresolved edges and per-template inherited CSS candidates (`7ea2a730`, `61b0912a`). Conditional includes are NOT guaranteed rendered; no CSS deletion without browser/owner evidence. Audit regression fixture lives solely in existing `scripts/test_audit_css_dependencies.py` (`6d7b3bd`) instead of duplicated in staff layout tests (`ef023edc`). Existing CI already runs this canonical test.
- PostgreSQL GitHub Actions job now runs the three existing real-service quantity/return/tenant regression cases (`a8970627`); execution result unverified.
- **Important P04 defect fixed in source:** `staff/base.html` had a 15-minute retail JS idle timer, but `StaffTerminalIdleMiddleware` enforced `PIN_IDLE_SECONDS=120` for every business line. Shared `staff_pin_idle_seconds(request)` in existing middleware now gives 900 seconds only for an authorized retail/supermarket outlet or a retail-only workspace; otherwise 120 seconds. The existing staff context processor passes the exact same value to browser JS (`c8fb80e8`, `23e4e1a6`, `18b6438a`). Test `60db2133` checks dedicated retail, shared bar and untrusted other-tenant outlet selections. **Tests and live two-terminal/browser flow remain unverified**. This is a general business-line policy, not hardcoded to Fizo.
- Do not call P00/P01/P03/P04/P15 complete. Next verification: CI at committed SHA and browser terminal unlock/lock behavior across tenant/outlet roles, then check approved UI and CSS dependency report.

## Checkout roadmap implementation — 24 October 2026, P06/P07/P15

The retail quantity AJAX success handler previously changed a header and one payable value but **left the approved right-hand basket subtotal/tax/due, Pay CTA and cash-change calculator stale**. Replaced that incomplete handler in the existing `order_detail_supermarket.html` with `updateBasketAmounts`; the fallback GET reconciler now also refreshes the same totals and calculator. The payment form's original due is updated only when it was not deliberately edited and no cash tender was entered. Commits `e6918714`, `48095cf9`, `9129aa3c`. No new JavaScript or CSS files.

Regression source contract was added to the existing `test_fizo_retail_sales_layout.py` (`e8345b49`), and a database-backed test asserts UGX total/paid/due after editing a part-paid basket (`c77185db`); PostgreSQL CI now includes it (`766e1906`). These are **committed, not executed here**. Do not call quantity UI production verified until post-deployment +/−, gross/due, cash/change, customer display and refresh are inspected. Continued checklist stays incomplete. Prevent new JS shadow scripts from duplicating these totals.

## P05/P06/P07 held-basket completion batch — 24 October

Previous "Resume" on the supermarket held-sales lane was a normal GET, so it *displayed* a parked sale but did not unhold it. The POS-entry lookup filters for `table_label=""`, so that same basket remained excluded from active registers. The canonical service `resume_held_retail_order` now clears `table_label` under an order row lock, checks tenant/outlet, open status and retail type, records an audit event, and preserves the order ID, payment ledger, receipt number and amounts (`5ed603cf`). It is re-exported through the existing POS commands and package API; staff order-detail POST `resume_order` honors tenant/outlet and staff permission guards (`fea32b5c`); the existing held lane now has a CSRF POST form (`3b04b39f`). No new routes, CSS or services.

The existing cashier regression module includes partial payment + hold + second basket + explicit resume, replay, cross-tenant rejection and closed-sale refusal (`2c87cd63`). Existing PostgreSQL CI targets include the two new tests (`4de90917`). **Do not claim tests or live checkout passed until CI execution and deployed browser verification are seen**. Continue the coupled customer display and receipt acceptance across active, held, resumed and paid baskets.

## 24 October continuation — all-outlets held basket retrieval

`StaffOrdersListView` filtered held-basket receipt/note searches only with a single selected retail outlet. With authorized all-retail outlets selected, the 50-card cap meant older held baskets could not be found through the lane. Source change `d6e9d3f7` extends the search over the existing tenant/membership-scoped queryset only when the outlet selection is a retail register or every accessible outlet is retail. Regression `d1ab7992` includes two authorized outlets and 51 newer held baskets; PostgreSQL CI includes it in `4129fde3`. Do not use this as evidence that all tenant permissions or browser workflows were accepted; focused and full tests, real-browser acceptance and screenshot matches remain pending.

## 24 October — P05/P06/P07 customer-screen state and privacy

The existing customer display previously trusted the active session pointer without excluding held orders. Commit `8e57d191` makes activation and active selection explicitly reject nonempty `table_label`, even if session state is stale. Customer display markup now carries actual server due (`1caaed2b`), and the existing polling JS refuses outdated local cash tenders and updates the due marker (`3c4fc064`). After three consecutive refresh failures (including expired PIN/session redirect) polling clears prior customer items to a neutral paused state rather than leaving them exposed forever (`00b3ad68`).

Holding the basket discards only its browser-local cash tender preview (`e138cfa4`, `67482e72`) while keeping all recorded tenders in PostgreSQL. Added a database-backed test for stale-pointer held → idle → explicit resume (`3678674e`), existing staff contract tests for customer-screen privacy (`e246609c`) and hold tender cleanup (`5b86ff3d`); PostgreSQL CI includes the database integration test (`801a6204`). **These tests have not been observed passing in this session**; deployed multiple-tab/monitor and five-viewport acceptance remain pending. No new CSS, controllers, routes or migrations.

## 24 October receipt/printing correction (P04/P07/P15)

`staff/order_print.html` had bypassed the shared staff terminal policy with `setTimeout(lock, 115000)` and the obsolete global `staff-terminal-lock` signal. It now uses the same server-derived `staff_pin_idle_ms` and tenant/user scoped lock key as the shared staff shell (`9c4d1f54`). The receipt labels tax, refunds, net paid and balance in the original order currency and distinguishes completed paid sales from still-outstanding partial ones (`cd2d1135`). Original payment amounts and ledgers are untouched.

Updated source checks in `test_fizo_retail_sales_layout.py` (`83a05e11`); fixed obsolete "Resume & collect balance" assertion in the existing cashier integration test and added completed/part-paid rendered receipt assertions (`09c9a963`, `c53b2eae`); both receipt paths are targeted in existing PostgreSQL CI (`9f56dc0e`). These changes need focused CI and physical thermal/A4 browser verification; commit status had no reported statuses when checked. No accepted roadmap phase.

## 24 October P06/P07 final customer-screen settlement acknowledgment

The completed-sale branch in the prior customer display HTML was unreachable because the monitor deliberately selects open/unpaid baskets only. Added a time-bounded (12 seconds) completion marker in the existing Django session for the active retailer's outlet/register, triggered only after `record_order_payment` returns an order that has actually closed/settled. The existing customer monitor idle template now shows a generic “Payment complete. Thank you” for this short interval, with **no previous product lines, bill reference, amounts or tender metadata**; subsequent sales clear it. Changed existing files only: `views_customer_display.py` (`6cd4a76b`), `views_ops.py` (`fb1be10d`) and `pos/customer_display_idle.html` (`0223e9af`). The implementation preserves the prior rule that closed orders never reactivate.

An earlier mixed-payment receipt test expected UGX while it instantiated a sale without currency; `e279f2b8` fixes the fixture. Added a database test that verifies customer-display thank-you, no old items/amounts, no reopening paid checkout, and marker expiration (`8345bc15`, `6dddb1e8`); PostgreSQL CI explicitly includes it (`c1e3a7c4`). **None of these CI or live browser results is verified in this session**. Next: inspect CI failures before deployment, run cashier + monitor and receipt browser acceptance, then approved UI 5-width parity.

## 25 October: parked retail sale cannot be edited or paid until resume (P05–P07)

The newly added hold/resume workflow was bypassable by existing checkout tabs and direct POS service callers. Under `StaffOrderDetailView.post`, a held retail basket now rejects ordinary sale mutations and fresh payment with a clear message (AJAX quantity returns HTTP 409, no HTTP 500); supervisor refunds remain separate. `get_context_data` hides quantity/payment forms for held retail baskets, and the existing order-detail template shows the original hold reference, payment already received, remaining balance and a CSRF POST “Resume this basket.” Commits `17c0f11a`, `41be46d0`, `4b233a23`.

Enforced below the UI in the existing `apps.pos.services.orders.require_active_retail_basket`: item/service additions, line void, quantity/discount/promotion updates, and new payment tenders are blocked on held supermarket/retail orders; hospitality table labels are not interpreted as held. Matching payment-idempotency retries are preserved before the guard. Commit `d80ca098`, `d9563ccc`, `e30f280e`. Also repaired PostgreSQL-invalid nullable `menu_item` join locking *in the actual line-discount service* (`a4e18bd2`). Test changes include direct service denial, nullable-line discount SQL lock, stale checkout tab, partial payment and explicit resumed checkout (`d75f0472`, `d69249c9`, `961e94ab`, `73a8aca5`, `b3011e92`, `fe8a2cf2`); the PostgreSQL CI job lists them (`39e56bf9`).

**Status:** changes committed directly on `main`, not executed on a disposable PostgreSQL DB or live browser in this session. Run focused suite and CI, inspect failed cases, and test hold/active/payment across multiple registers. Do not mark these phases accepted or claim deployed fixes.

## 25 October — P06/P08/P15 checkout barcode, PLU and weighted-source integrity

Root fix in **existing** `backend/apps/pos/services/orders.py`: previously scanner added/merged a line under an order lock, then overwrote `line.pricing_source` with a second write outside that transaction, corrupting provenance after barcode/PLU merges. `add_line_to_open_order(..., pricing_source="menu")` now validates and sets source at creation; merging keeps prior source, while `add_supermarket_line_by_code` chooses barcode, PLU or weighted source before invoking that same canonical transaction (`49f1b381`). Existing measured items remain separate. No extra scan handler or migration.

The cashier's `catalogue_q` and staff product `q` now search active tenant-scoped supermarket PLU codes in the same outlet-authorized product query, in addition to name, SKU and barcode (`bcd9b025`, `ca91360f`). Tests in the **existing** `backend/tests/test_supermarket_cashier_lane.py` cover barcode→PLU merged line source and total, weighted quantity/source isolation, both catalogue search screens, inactive PLU and foreign-tenant data (`d59c56c4`, `400b5c21`, `f5f4f661`), targeted by PostgreSQL CI (`b7f7f993`, `cc180b54`).

**Not yet executed in this session:** Django integration tests against a disposable PostgreSQL DB, live browser/barcode scanner and tenant-specific physical device acceptance. Do not mark P06/P08/P15 finished. Next inspect test run outcomes, then test real scanning (including weighted scale labels), inventory consumed on final settlement, held/recalled baskets, and 5-width approved UI screenshots.

## 25 October: stock checkout cannot overdraw item also consumed in recipe (P07–P09)

Existing `backend/apps/inventory/services.py::validate_and_consume_stock_for_paid_order` independently checked direct POS sale stock and recipe ingredient stock. If the same tracked SKU was both a sold line and a BOM ingredient in the order, each pass could approve demand independently, leaving a **negative balance after two valid-looking deductions**. Commit `48e3fa7b` aggregates both requirements, locks every affected StockBalance deterministically and rejects combined shortage **before any write**; then it still posts individual SALE and RECIPE movement reasons and existing FEFO batch allocations inside the payment transaction.

The existing supermarket integration test now covers actual financial rollback on shortage and successful later settlement after the same inventory receiving service posts the missing unit. For example, quantity 4 versus sale 3 + recipe 2 rejects payment and leaves sale open/stock unchanged, receiving +1 permits payment, and creates separate SALE -3 and RECIPE -2 movements (commits `1bb943f6`, `8780e70c`, `dfd16845`). Existing PostgreSQL CI includes the case (`574a9cff`). **CI and live PostgreSQL/browser execution not verified.** Further P09 PO goods receiving, multi-outlet transfers, expiry batches and 5-width UI acceptance remain pending. No new files, schemas or alternative stock service.

## 25 October P08/P09: usable cashier stock (not quarantined physical balances)

Existing cashier catalogue product tiles were stock-blind. `views_ops.py` now batch-loads outlet-scoped balances for the visible product page, marks zero and below-reorder statuses (`9fd77efe`), and calculates saleable FEFO quantity from non-quarantined/non-expired InventoryBatch records, capped by StockBalance quantity (`fa47cd1f`). The existing `fizo_pos_catalogue.html` tile displays Sellable, Low stock, No sellable stock and a held/expired batch note (`f54f23d6`, `e5a21b69`); existing `retail-cashier.css` contains compact responsive styling (`733881ca`). Never label this a stock reservation: the actual transaction still validates stock at settlement.

Tests in `backend/tests/test_supermarket_cashier_lane.py` cover zero/low/adequate stock and selected-outlet isolation, plus quarantined/expired FEFO balances (`a32fc39c`, `ce339cdf`). PostgreSQL quality CI explicitly includes both (`8eafd600`), but **there is no observed passing result, screenshot parity or live tenant verification**. Avoid creating a second inventory query service or a new tile CSS. P08–P09 and P15 remain open.

## 25 October: retail displayed price now matches actual outlet sale

A retail catalogue tile formerly rendered the global `item.unit_price` even when `add_line_to_open_order` charged `item.unit_price_for_outlet(outlet_id)` using an outlet-specific override. `views_ops.py` now looks up nonnull `MenuItemOutlet.price_override` records for only the displayed products at the current outlet/tenant, attaches `cashier_display_price`, and the existing `fizo_pos_catalogue.html` shows it only on retail screens (`d3b18f9c`, `a1c37a1b`). Existing integration test `5dadb053` verifies UI selling price and committed line/total match; CI adds the case (`d54c9f7b`). Not independently run or visually verified.

## 25 October P09 receiving preflight and duplicate delivery protection

The canonical purchase-order receiving service in `apps/purchasing/services.py` now preflights all positive receipt rows, ordered quantity remaining, batch-code requirements and existing batch codes **before creating a receipt or stock movements** (`6bbba3c8`), and removes the now-duplicated checks inside its posting loop (`e7fa777a`). Existing atomic transaction, PO lock, membership/outlet gate and case-insensitive supplier delivery-reference check remain the execution boundary. Do not introduce another receiving handler.

Existing regression `test_purchase_delivery_preflight_and_duplicate_reference_keep_stock_accurate` (`bf6cb496`) checks invalid second line leaves no PO receipt/stock effects, valid partial receipt posts balances and updates PO status, then repeated supplier reference leaves stock untouched. PostgreSQL CI includes it (`fd07baad`). **Tests not executed and production flow not browser-accepted**. Next verify CI, carton conversion and expiry batch receipt against live cashier availability.

## P09 carton representation parity — 25 October

The central `to_stock_units` accepts `"1.0"` as a whole carton, but purchase receiving later tried `int("1.0")`. `ae591cff` normalizes using Decimal after validation. The existing PO regression `8d1c1982` now covers a second delivery completing the PO via one two-unit carton, including final PO status, stock and carton count. CI target remains in quality.yml; no passing result verified.

## Delivery workstream D00–D07 — 25 October 2026

Decision: keep ordinary first-party restaurant, supermarket, retail, bar and hotel deliveries in the *same* multi-tenant POS as an optional separate fulfillment workflow. Do not build a parallel order, payment or stock ledger and do not repurpose `RetailPickup` to represent courier dispatch. Details: `docs/DELIVERY_FULFILLMENT_IMPLEMENTATION_2026-10-25.md`.

**Implemented D00 only:** Pure policy in `backend/apps/pos/services/delivery_policy.py` validates outlet-type support, external address versus hotel-room delivery, state transitions, currency-aware fees and paid-only assigned-driver dispatch (`2f2702dc`, `440ef98d`). `backend/tests/test_delivery_policy.py` covers these contracts (`4f1daa1c`, `97a0381d`); the existing PostgreSQL quality workflow includes them (`8ed722b9`). None of the policy code writes orders, delivery rows, money or stock.

**Not implemented:** delivery model/migration, enablement per outlet, staff order-entry/dispatch screens, printed slip, rider assignment, courier API, COD, delivery fee posting and public customer tracking. D01 needs one migration-backed `OrderDelivery` model scoped to tenant/outlet with an order one-to-one key and explicit role permissions; verify latest migration dependency and run schema checks before committing it. D02 paid-only retail fulfillment should hook existing `Order`, `Payment` and `StockMovement` once, not re-post on dispatch. Expand D03 restaurant KDS, D04 room/folio, D05 legal bar delivery, D06 COD and D07 third-party integrations progressively.

**Do not claim delivery is working or deployed.** Tests still need actual CI status, and live checkout/KDS/hotel/receipt/mobile viewport acceptance remains unsatisfied.

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
