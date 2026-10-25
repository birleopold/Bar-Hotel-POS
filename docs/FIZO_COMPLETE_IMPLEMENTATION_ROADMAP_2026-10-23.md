# Fizo complete face-by-face implementation roadmap

**Version:** 2026-10-23 · **Target branch:** `origin/main` only · **Status:** PLANNED (not implemented by writing this roadmap) · **Inventory base:** `d02d3768ed3df7e1ed4e9aacfe22c106eb8125d2`

## Non-negotiable engineering contract

1. Research operational workflows before implementation; adopt the simplest professional-grade sequence and confirm exceptions.
2. Work directly on `main`, push to `origin/main`, never create feature branches for this programme.
3. Supplied approved images are acceptance references: align proportion, spacing, color, typography, controls, responsive behavior and real data. Record per-template image baseline, viewport and measured discrepancy.
4. At most **two shared CSS foundations**, plus justified line-specific stylesheet(s). CSS ownership is exclusive; eliminate duplicate selectors, `!important` escalation, legacy imports and inline overrides before completion.
5. No patch-on-patch: trace failing flow to source; directly replace faulty selector, handler, template or service and delete superseded implementation in the same change after dependencies pass. No overlay-only fixes.
6. Every screen feature must exist from URL/permission through backend, state, template, interaction, validation, persistence, navigation, printing and tests; no mock/demo values in production.
7. Strong isolation for supermarket/grocery, restaurant, bar and hotel: tenant data boundaries, enabled capabilities, branded navigation and terminology; unrelated functionality must not leak.
8. Make sensible UX corrections without repeated confirmations; minimize clicks and reading and prioritize frequent tasks.
9. Preserve data, migrations, production integration behavior and existing working business flows; changes must be reversible through a safe deploy/rollback.
10. Run browser acceptance at desktop 1536×1024, laptop 1366×768, tablet 1024×768, mobile 390×844 and wide 1920×1080; both mouse/keyboard and touch; inspect reference pixel differences, text overflow, controls, focus, empty/loading/error states.
11. Every phase completion needs source-level tests, rendered checks, full navigation, permission/currency test and owner signoff against screenshot before marking complete.

## Cross-phase feature completion rule (24 October 2026)

When a problem in the current P00 verification phase concerns a feature also scheduled in another phase, **complete its directly related work in the same implementation package** instead of revisiting the same component later. Example: a hotel dashboard change includes its relevant P02 accessible shared components, P03 site/tenant authorization, P12 front-desk and housekeeping operations, P13 multi-module navigation, and P15 regression/viewport checks. For cashier changes, bundle relevant P01/P02/P03/P04/P05/P06/P07/P08/P09 checks. Unrelated workstreams remain independent.

This **does not bypass any acceptance gate or mark later phases complete**: record a cross-phase partial implementation with changed sources, permission/tenant/data checks, tests, viewport evidence, and unresolved requirements. Keep the phase order for unrelated work and overall signoff. Avoid duplicate template/controller/style ownership by completing all directly affected existing owners in the same change.

## Parallel implementation bundles (required for every P00 discovery)

The sequential gate controls **signoff**, not development order. Every source component discovered in P00 must be implemented with its directly related later-phase work before it is treated as a finished change. Do not reopen the same CSS owner, form, service or menu in a later phase merely because a related concern was deferred without an explicit dependency.

| Integrated package | Implement together, whenever touching the same feature | Coverage to record before claiming that package ready |
|---|---|---|
| Shared visual shell and auth | P00 inventory + P01 canonical CSS owner + P02 responsive/accessibility + P03 tenant theme/terminology + P04 login/idle-lock + P13 optional modules + P15 viewport regression | Desktop, laptop, tablet, mobile, wide; keyboard/touch; signed-in roles; single-line and multi-line tenant |
| Retail sales/cashier | P00 route evidence + P01/P02 styles and shared controls + P03 outlet scope/currency + P04 till identity + P06 approved register + P07 stock/payment/returns/idempotency + P08 product/UOM/image + P09 cash reports + P15 receipt/viewport verification | Real barcode/product search, single-submit, whole vs measured quantity, UGX, cash/mobile-money flows, receipt, shift and denied-role paths |
| Retail catalog and receiving | P00 dependency map + P01/P02 forms/layout + P03 tenant/outlet permissions + P08 image-from-phone/import/stock + P09 purchasing/suppliers/reports + P15 mobile/desktop continuation | Image attachment from a separate phone or desktop, import missing-image follow-up, supplier ledger, opening inventory, two tenants, errors/duplicates |
| Restaurant and bar | P00 inventory + P01/P02 shared tokens/navigation + P03/P04 access + P10 restaurant service + P11 bar tabs/rounds + P13 mixed modules + P15 end-to-end acceptance | Each standalone line's own terminology, routing, receipts, tables/tabs, role controls; enabled combinations never contaminate a standalone screen |
| Hotel and front desk | P00 inventory + P01/P02 shared screen ownership + P03/P04 staff access + P12 reservations/rooms/folio/housekeeping + P13 optional services + P15 acceptance | Reservation conflicts, room status, checkout, folio and night audit, mobile housekeeping and isolated tenant permissions |
| Platform/security/commercial | P00 architecture/CI + P03 isolation + P04 recovery + P09 finance/owner reports + P13 entitlements + P14 tenant subscription/admin + P15 deployment/safety | Two-tenant negative tests, UGX and selected business settings, authorization at template AND service, migrations, recovery and audit trails |

**Batch completion protocol:** (a) locate existing route → view/service → template → CSS → tests; (b) inspect the relevant later phase and linked 34-item/retail checklist; (c) implement all directly coupled code and regression tests in one coherent batch; (d) record verified vs unverified capabilities in both checklists; (e) use exact-SHA CI, cross-tenant browser acceptance and source/reference screenshots as signoff, leaving gaps open. Fix shared foundations once; use specific business-line overrides only for distinct behavior. Avoid artificial commits merely to tick a phase.

## Cross-phase implementation pulse — 24 October 2026

**Acceptance and coding are separate.** The original sequential phase gate remains P00 in progress, and **no P01–P15 phase has passed its full owner/UI/CI/production exit criteria**. The checkboxes below therefore represent actual cross-phase code progress, not completed phases. The long-running 34-item suite board separately records 4 historically locally verified foundations and 30 incomplete workstreams. They are not the same denominator.

| Integrated P work | Evidence already committed | Still blocking phase completion |
|---|---|---|
| P01/P02 | Shared surface CSS and component work exists | CSS reference inventory, approved viewport screenshots, a clean whole-project test run |
| P03/P04 | Tenant currency guards and session/register-scoped client-screen pointer | Cross-tenant/live register scenarios, PIN and idle behavior across line types |
| P05/P06 | Retail cashier, customer screen, basket hold and resume tools | Pixel-parity on all approved screens; live two-screen automated acceptance |
| P07 | Partial/mixed payment, hold, duplicate-submit, change and receipt test coverage | Correct full checkout end-to-end, provider confirmation and complete green CI |
| P08/P09 | Stock catalogue, buying, and reconciliation foundations predate this pulse; currency-linked shift test improvements | Supplier workflow, FEFO, stock movement and till count audits |
| P10/P11 | Existing kitchen/bar KDS status and station routing; retail prep exclusion committed | Hospitality role/route, ready-to-served sequence and real station screens |
| P12/P13/P14 | Existing hotel, entitlement and platform foundations in 34-item tracker | All hospitality/entitlement/subscription operational acceptance |
| P15 | Checkout/receipt/display/CI regression tests and deployment checks | CI failures, device scenarios, browser viewport and production release evidence |

CI example at `896f27e`: PostgreSQL integration job passed, SQLite checks failed with 28 failures out of the suite; newer runs need exact-SHA verification. **Do not report a phase percentage by dividing cross-phase commits by requirements**; that would misrepresent progress.

## 24 October implementation checkpoint — P00/P07 coupled PostgreSQL row locks

- P00 discovery traced an actual production quantity-edit HTTP 500 to PostgreSQL rejecting `SELECT FOR UPDATE` of a nullable `menu_item` outer join. The precise quantity service (not the superficially similar discount code) was corrected in `0bea9ce6`, with the prior mistaken discount edit reverted. Production/browser verification of +/−, totals and persistence remains **open**.
- P07 shared financial transaction work: inspected `process_supermarket_line_return` in the existing `backend/apps/pos/services/orders.py`. It had the same nullable-join locking defect for service/non-product lines. Replaced **only that query** with a row-only lock in `fed8494b`; existing restock, paid-order and return-quantity checks remain unchanged. Added a real-service-line return regression in `e3cd7c65` to the existing supermarket cashier test module. No new CSS, services, templates, routes or migrations were introduced.
- Documentation basis: Django QuerySet `select_for_update()` explicitly documents PostgreSQL's nullable-relation outer-join restriction and `of=("self",)` row-only locking. Evidence **not yet collected**: passing PostgreSQL test run at these commits, full CI, device/browser baseline, denied tenant/role paths, live return workflow and owner visual approval.
- **Phases remain P00 in progress and P07 partially implemented/unaccepted.** Do not change the historical 4/34 suite count or declare a phase finished.

### P00/P03/P07/P15 regression hardening — 24 October, follow-on

- The PostgreSQL nullable-product lock change was extended only to the existing line-return service, with no new controller or stylesheet. Tests in `backend/tests/test_supermarket_cashier_lane.py` now inspect captured PostgreSQL locking SQL to reject nullable LEFT OUTER JOINs (`bfc77761`) and exercise an attempted cross-tenant line return (`1c7cd8c9`). These cover P03 tenant isolation, P07 transaction correctness and P15 SQL-level verification together.
- **Evidence status:** code committed and fetched back from main. The focused tests have **not yet been executed**, and no PostgreSQL test-environment, current GitHub CI outcome, five-viewport screenshots or deployed browser acceptance evidence has been collected for these commits. P00 is still in progress; no phase completion marker changed.
- Before deploying, run focused tests against a disposable test database and check the complete action log. Do **not** run the test suite against production PostgreSQL or create cross-tenant test data in real tenant accounts.

### P00/P02/P03/P04/P06 implementation bundle — 24 October, late session

A shared-shell source review identified and corrected real navigation and staff-context defects without new CSS/controller files:

- **P03/P04 isolation:** the existing `staff/base.html` used a global `localStorage` lock event key for all tabs on one browser origin. `c97a3d2` scopes lock signals to the active tenant and authenticated user, retaining cross-tab lock synchronization for the same operator. Separate tenant and account workspaces no longer consume each other's broadcast in this handler; device/session browser acceptance pending.
- **P06 cashier:** `staff/includes/nav.html` pointed the universal “POS” shortcut to the order history screen. `328a51a` sends supermarket/retail cashiers to `staff-retail-pos-entry` and labels the hospitality shortcut “Orders”. The existing sidebar POS route was already correct.
- **P02 staff identity:** `795aa7f` adds the authenticated operator's actual display name/email to the existing shared header, neutral wording refined in `8eaffc7`. The existing `fizo-fresh.css` now handles narrow and mobile screens (`c119a1d`); no line-specific stylesheet added.
- **P15 checks:** `ad4915c` adds source-level regression checks for tenant-scoped lock events, retail register routing, visible operator identity and foundation CSS. `scripts/audit_css_dependencies.py` now records exact duplicate stylesheet references within one tracked template/source (`7e842a4`), as **warnings**, not grounds for deletion without dependency and browser review.
- **Evidence status:** these commits are source changes only, not five-viewport screenshot acceptance, execution of the full suite, fresh CSS audit output, live same-user/multi-tenant terminal behavior or hardware/provider certification. P00 and P01–P15 acceptance remain open. No migrations or financial writes introduced.

### P00/P01/P02 foundation ownership — additional source cleanup (24 October)

- Refined the **existing** `scripts/audit_css_dependencies.py` so duplicate stylesheet warnings are tied to actual HTML template references, not arbitrary JavaScript/CSS text. The report still lists missing references, import edges and unreferenced *candidates*, without deleting any assets (`2017ceeb`).
- Added a focused temporary-file fixture in the **existing** staff regression test module to assert missing CSS and repeated template links are correctly detected while a referenced stylesheet is not called unreferenced (`6a020c0`). This test has not yet run in CI.
- Removed a mathematically redundant mobile `.fizo-dash__roomgrid` breakpoint rule from the **existing** `fizo-fresh.css` (`f4d1e402`), keeping the 550px two-column breakpoint and the independent 480px card sizing. No stylesheet was created; no deletion of unverified business-line CSS.
- **Acceptance:** P00 still open. Current runtime stylesheet dependency counts, five-size screenshot parity, accessibility audit, CSS cascade measurements and focused/full CI remain unverified. This is limited P00/P01/P02 source progress, not completion or production certification.

### P00/P01/P03/P04/P15 integrated delivery — 24 October follow-on

**Implemented in existing files, pending CI/browser acceptance:**

- P00 CSS ownership: `scripts/audit_css_dependencies.py` now reports literal Django `extends`/`include` relationships, unresolved template links, dynamic inclusion candidates and inherited CSS candidates for each tracked template. The graph is **not proof** that conditional branches render together. Commits `7ea2a730` and `61b0912a`; the original report remains available.
- P01 audit test ownership: moved the temporary-file CSS graph/duplicate/missing-asset fixture into the **existing** canonical `scripts/test_audit_css_dependencies.py`, which already runs under CI (`6d7b3bd`). Removed the duplicate fixture from cashier tests (`ef023edc`). No new test or CSS files were created.
- P15 PostgreSQL coverage: `.github/workflows/quality.yml` now explicitly executes the real quantity-lock, nullable service-return and cross-tenant-return regressions against PostgreSQL, not only SQLite (`a8970627`). This is a CI gate, **not evidence it passed**.
- P03/P04 cashier terminal: source review exposed a genuine contradiction: client allowed retail PIN idle for 15 minutes but `StaffTerminalIdleMiddleware` rejected sessions after a fixed 2 minutes. `staff_pin_idle_seconds(request)` now derives the limit from an *authorized, tenant-matching selected outlet* (retail/supermarket 900 s, shared hospitality 120 s); for an unselected outlet the longer limit is available only to retail-only businesses. The staff context processor exposes the same policy to the existing browser timer, replacing both duplicated client constants. Commits `c8fb80e8`, `23e4e1a6`, `18b6438a`. An unauthorized/foreign outlet cannot extend a PIN session. Regression test `60db2133` covers dedicated retail, shared bar and foreign tenant selection.
- **Outstanding:** execute the updated CI, PostgreSQL and CSS audit; browser-check both timer modes, all outlets, mobile tabs, exact approved screenshots and cashier +/−. No phase signoff; no migrations or production payment changes; no new stylesheets or alternative handlers.

### P06/P07/P15 integrated checkout consistency — 24 October continuation

- **P06/P07 source defect identified:** the existing AJAX quantity response updated only `.staff-pos-totals-row__total strong`, `.staff-pos-totals-row__meta` and the headline payable figure, but not the approved **right basket** subtotal, tax, total due or cashier Pay CTA. The cash-change calculator also cached `dueRaw`/`dueCents` from page load. Customers could therefore see contradictory amounts after a successfully committed line edit.
- **Canonical fix in the existing checkout template**, not another CSS/JS file: `order_detail_supermarket.html` now has one `updateBasketAmounts` renderer for POST success; it updates the basket subtotal/tax/due, header, Pay CTA and cash-change calculator. Its GET reconciliation also restores those amounts from actual server HTML, and emits the existing-panel balance-change event. The payment amount follows the revised balance only while it still represents the old automatic due and there is no cash tender input, preserving a deliberately entered partial payment. Commits `e6918714`, `48095cf9`, `9129aa3c`.
- **P15 coverage:** existing staff layout contract now checks checkout total and tender synchronization (`e8345b49`); existing cashier integration test checks that a quantity increase on a UGX partially paid basket returns the correct line amount, gross total, paid and due, and persists in the database (`c77185db`). PostgreSQL CI explicitly includes the new case (`766e1906`).
- **No phase accepted:** tests are committed but their actual results, cross-tenant/role browser verification and viewport screenshot parity remain pending. No migrations or extra CSS/service/controller files. Hold/resume and partial-payment operational acceptance remains required; preserve accounting and idempotency safeguards.

### P05/P06/P07/P03/P15 integrated held-basket workflow — 24 October continuation

**Functional implementation (not just planning):** Previously, the retail held-lane "Resume" anchor performed a GET to an order, leaving `Order.table_label` set. The same basket therefore remained classified as **held**, instead of becoming the cashier's active sale. A proper resume must be a state-changing POST.

- Added `resume_held_retail_order` to the existing transactional POS order commands (`orders.py`, re-exported via existing `commands.py`/`__init__.py`). It locks and tenant/outlet-scopes the original order, permits only open/not fully paid supermarket/retail orders, clears the held label, and audits `order.resumed`. It never creates another order, refunds, new payment or settlement. Repeating the action on an already active order is safe.
- Extended existing `StaffOrderDetailView` with permission-checked `resume_order` POST and redirect to the original basket. This leaves the standard get_queryset tenant/outlet protections in place and does not affect restaurant/bar/hotel tabs.
- Replaced the retail held-lane passive anchor with an authenticated CSRF-protected **Resume basket** form. The existing retail POS entry selects active unlabeled baskets, so after resume it can find the returned original basket instead of leaving it parked. Held-basket listing and payment summaries remain visible before resume. No page-specific CSS or new routes.
- Added tests in the existing supermarket cashier test file for partially paid hold → serve a different customer → POST resume → preserve original balance/receipt/order/payment, duplicate resume, cross-tenant denial, and closed-sale rejection. Explicit PostgreSQL CI targets include both tests.
- **Commits:** `5ed603cf`, `8113ba10`, `f1a9a434`, `fea32b5c`, `3b04b39f`, `2c87cd63`, `4de90917`.
- **Open acceptance:** Run focused and full CI at latest SHA, real tenant browser test for two baskets and partially paid resume, customer display/receipt and 5 approved UI viewport comparisons. All phase gates remain unaccepted. No migration, new CSS, alternate controller, or prod-data writes from this commit workflow.

### Held-basket retrieval multi-outlet completion — 24 October

Follow-on to the explicit retail resume workflow: `StaffOrdersListView` previously restricted held-basket note/receipt searches to the **single selected retail outlet**. In an authorized all-outlets retail-only view the held cards were capped at 50, but a search could not narrow that list to older held sales. `d6e9d3f7` now applies search across the existing membership-scoped outlet queryset when all accessible outlets are retail/supermarket; mixed hospitality scopes remain neutral and restricted. `d1ab7992` adds a regression with two authorized retail outlets plus 51 newer parked baskets, and `4129fde3` includes it in PostgreSQL CI. This does not relax tenant or outlet access.

The original sale, received partial tenders and outstanding balance continue to be preserved on POST resume. **Execution of new tests, browser acceptance, visual parity and deployment remains pending**; do not mark P05/P06/P07/P15 signed off.

### P05/P06/P07/P15 second-screen privacy and state coherence — 24 October

- **Held basket safety:** `mark_customer_display_active` now refuses an order with a hold label; the customer-display GET query also requires `table_label=""` even when an obsolete register session pointer survives. This prevents a held sale from being redisplayed by a stale customer-monitor URL. Commit `8e57d191`.
- **Cash tender safety:** customer display now carries an authoritative current balance; `customer-display-live.js` hides a local transient cash tender whose due amount no longer matches the server balance and refreshes its due marker on poll. Commits `1caaed2b`, `3c4fc064`.
- **Auth/privacy safety:** after three failed or redirected polling requests, the customer monitor clears the previous shopper's items and displays a neutral paused message instead of retaining a potentially private basket indefinitely or navigating to a staff login. Commit `00b3ad68`.
- **Held-basket cleanup:** retail basket template exposes only its current order UUID to the existing `retail-counter-v2.js`, which clears the *uncommitted* cash-tender localStorage preview on hold submit. Recorded payments remain server-side. Commits `e138cfa4`, `67482e72`.
- **Regression gates:** database integration test uses a deliberately stale pointer, holds the order, checks customer monitor idle, and resumes by POST; existing staff contract tests cover expired-session blanking, stale balance and transient tender clearing. Commits `3678674e`, `e246609c`, `5b86ff3d`; PostgreSQL CI includes the stale pointer integration test (`801a6204`).
- **Evidence still missing:** CI results, actual browser monitoring on separate display through hold/resume/payment, multi-tab auth changes, five approved viewport screenshots, and deployment. These commits do not establish P05/P06/P07/P15 completion.

### P04/P07/P15 receipt/terminal consistency — 24 October late continuation

- Inspected `StaffOrderPrintView` and `staff/order_print.html`. The print page still used a global `staff-terminal-lock` localStorage broadcast and a hardcoded 115,000 ms timeout, contradicting the shared register policy (15 minutes on an authorized retail till, 2 minutes on shared hospitality terminals). Replaced **the existing print-page handler** to use the same `staff_pin_idle_ms` context and tenant/user-scoped lock key as `staff/base.html`. No new JS/CSS, route or middleware module (`9c4d1f54`).
- Thermal/A4 print payment summary now clearly labels sale currency for tax, refunds, net paid and remaining balance. Added a paid-in-full state for closed/settled orders and a distinct outstanding-balance state for partially paid orders. These states are derived from existing `order_payment_totals` and stored status; no ledger changes (`9c4d1f54`, `cd2d1135`).
- Fixed an existing stale integration assertion that expected the deleted passive "Resume & collect balance" link; it now asserts the canonical CSRF POST form and "Resume basket". Added rendered receipt assertions for completed mixed-payment and partially paid sales, and source-level checks for print terminal lock/currency (`09c9a963`, `c53b2eae`, `83a05e11`).
- Included the two receipt integration cases in the existing PostgreSQL CI job (`9f56dc0e`).
- **Verification:** changes were committed directly on `main`; combined commit status reported no statuses at inspection. New tests and production printing **not observed passing**. P04/P07/P15 remain unaccepted; printer formats, tenant roles, mobile and all approved viewport comparisons still need end-to-end acceptance.

### P06/P07/P15 checkout completion and receipt regression correction — 24 October

- Existing thermal receipt print page was aligned with shared user/tenant-scoped terminal lock and real idle policy, with currency-explicit net payment and refund summaries. The prior mixed-tender receipt test created an order with implicit model-default currency, even though the new assertions expected **UGX**. Commit `e279f2b8` corrects the fixture to specify `currency="UGX"` rather than weakening the receipt assertion.
- **Customer-facing closeout bug:** `customer_display.html` already carried a full-payment thank-you branch, but the view deliberately selects only `status="open", is_paid=False`, making that branch unreachable. Existing `views_customer_display.py` now writes a **short, 12-second session-scoped completion marker** only on successful fully paid/closed retail settlement, clears the old active pointer, and serves the **existing idle template** with a generic thank-you without showing items, receipt details or tender values (`6cd4a76b`, `fb1be10d`, `0223e9af`). The next active checkout clears the acknowledgment. Once elapsed, the idle screen returns to its ordinary welcome.
- Existing database cashier test now covers the post-payment thank-you, absence of old customer items/payment values, a completed sale remaining inactive and explicit expiry (`8345bc15`, `b1ee3036`, `6dddb1e8`). Existing PostgreSQL CI includes this case (`c1e3a7c4`).
- **Acceptance remains outstanding:** CI and browser verification, multi-monitor session expiration, physical receipt print parity, and five-viewport approved cashier screenshot comparison. These commits are **source-implemented, not accepted or production-certified**. No new routes, CSS, migrations, or external services.

### P05/P06/P07/P15 parked-sale transaction boundary — 25 October continuation

- **Confirmed defect:** the held-basket lane used explicit resume, but a stale checkout tab or direct service/API caller could still change quantities or accept a new tender on a held retail order. Professional POS suspend/recall separates a parked sale from active checkout. The existing `StaffOrderDetailView.post` now returns a structured HTTP 409 for AJAX quantity writes against held baskets and redirects other ordinary edits/payments to the held-sales lane, while leaving supervisor payment refunds available (`17c0f11a`). The same existing checkout context hides payment/edit controls and renders hold label, prior payments, remaining balance and an explicit CSRF-protected **Resume this basket** action (`41be46d0`, `4b233a23`).
- **Enforced below the UI:** existing POS service `require_active_retail_basket` now rejects item/service additions, quantity edits, line void/discount, promotion changes and new payments to parked retail sales, without interpreting restaurant/hotel table labels as holds (`d80ca098`, `d9563ccc`, `e30f280e`). Previously recorded matching payment idempotency replays are checked before the new-payment guard, preserving retry correctness. Supervisor refunds remain separately permissioned.
- **PostgreSQL correctness:** the original nullable-join `select_for_update().select_related("menu_item")` still existed in `apply_supermarket_line_discount`. It is now corrected within that exact function using `select_for_update(of=("self",))` (`a4e18bd2`), matching the tested quantity and line-return pattern.
- **Regression work:** updated legacy mixed-payment scenario to POST resume before settlement (`961e94ab`), updated parked partial-payment screen expectation (`73a8aca5`) and added tests for stale-tab payment/quantity denial, active replay after resume, direct-service write rejection and nullable-service discount row locking (`d69249c9`, `b3011e92`, `fe8a2cf2`, `d75f0472`). Existing PostgreSQL CI job now lists the new cases (`39e56bf9`).
- **Not accepted:** CI test execution and real PostgreSQL outcomes not observed; production deployment, payment provider sandbox, cashier multi-tab, 5-viewport screenshot parity and physical printer test all remain pending. No new routes, models, CSS files, migrations or duplicate feature services.

### P06/P08/P15 catalogue-to-cashier scan integrity — 25 October continuation

- **Root defect removed:** `add_supermarket_line_by_code` previously called the transactional `add_line_to_open_order` and afterwards changed `line.pricing_source` in a second write. If that add merged a barcode, PLU or menu item into an existing basket row, the second write overwrote that row's earlier source; the source write was also outside the original order-row lock/transaction. `49f1b381` moves source selection *before* the add and passes an optional validated `pricing_source` argument into the canonical transactional add command. A newly created line has its correct barcode/PLU/weighted source immediately; a matching merged ordinary item retains its previous source without a post-transaction overwrite; weighed lines continue separate rather than merging with menu/barcode/PLU entries.
- **Consistent product lookup:** The cashier catalogue search previously matched only product name, SKU and barcode, although the scan handler accepts active PLU codes. `bcd9b025` adds tenant-scoped active PLU lookup in the *existing* cashier query. `ca91360f` applies the same search to the existing staff product catalogue, keeping each page's tenant/outlet permissions and capped result lists.
- **Tests added to existing cashier module:** barcode followed by PLU merges into one correct UGX basket line without corrupting its initial provenance; weighted barcode and PLU keep separate measured quantities and totals (`d59c56c4`); active PLU appears in both cashier and staff catalogue but inactive or another tenant's PLU does not (`400b5c21`, `f5f4f661`). Focused PostgreSQL CI targets include these cases (`b7f7f993`, `cc180b54`).
- **Acceptance:** Source committed on `origin/main`; no test execution, GitHub Actions pass, current database inspection, barcode-scanner hardware or browser verification evidenced in this batch. P06/P08/P15 remain partial. No new routes, CSS, DB migration, model, service module or duplicate scan handler.

### P07/P08/P09/P15 integrated stock settlement protection — 25 October continuation

- **Financial/inventory defect:** `validate_and_consume_stock_for_paid_order` previously checked tracked direct-sale demand and recipe-ingredient demand in two independent passes. When the **same tracked item** was sold as a product and also consumed as an ingredient on the same paid order, both validations could pass even though their **combined demand exceeded stock**; the second deduction could leave the outlet balance negative. In existing `backend/apps/inventory/services.py`, `48e3fa7b` now aggregates sale and recipe demand before any stock movement, locks balances in deterministic item order, rejects insufficient combined stock, then preserves distinct SALE and RECIPE movements on success. FEFO allocations remain within the same existing atomic transaction.
- **P09 receiving → P07 payment integration test:** existing `backend/tests/test_supermarket_cashier_lane.py` now checks a tracked item with 4 in stock, 3 directly sold plus 2 consumed as a recipe ingredient. The validation and real final-payment command reject the 5-item demand, preserving the open sale, unchanged balance, zero payments and zero sale movements. The test then receives one additional unit through the existing `apply_manual_stock_change(..., reason=RECEIVE)` service and settles the sale once; the final balance is zero and the ledger contains distinct SALE -3 and RECIPE -2 movements. Commits `1bb943f6`, `8780e70c`, `dfd16845`.
- **P15 CI:** existing PostgreSQL quality workflow now names this integration regression (`574a9cff`). This is **committed coverage, not a confirmed passing run**; real concurrent-checkout, receiving/expiry batches, outlet/tenant browser operations, five approved UI widths and production deployment still require acceptance evidence. No new migration, controller, CSS or duplicate inventory service was created.

### P08/P09/P15 cashier stock availability and FEFO visibility — 25 October continuation

- The existing retailer product tiles lacked any outlet on-hand feedback even though final payment already validates stock. `9fd77efe` attaches stock status for only the visible 80-product catalogue page using one tenant/outlet-scoped StockBalance lookup, with low-stock warnings based on the existing `reorder_level`. `f54f23d6` displays these labels in the canonical cashier tile; `733881ca` styles them in the existing `retail-cashier.css`. Tracked items with no balance display zero; untracked services/products do not receive false stock badges.
- **FEFO correction:** physical on-hand quantity can include expired, quarantined or previously unlabelled batch stock that the settlement service will not release. `fa47cd1f` adds one grouped tenant/outlet-scoped batch-usable query for the visible products and caps the cashier tile at the smaller of usable batch quantity and on-hand balance. The existing tile now says **Sellable**, **Low stock** or **No sellable stock**, with a held/expired-batch note when usable count is lower (`e5a21b69`). These labels are advisory; authoritative validation remains at settlement and still prevents negative stock.
- P15 regression tests in the existing supermarket cashier module check that the selected outlet never reveals another outlet's 90-unit balance, that on-hand zero/low/healthy statuses reflect the existing reorder threshold, and that only 3 of 12 physical items display as usable when 5 are expired and 4 quarantined (`a32fc39c`, `ce339cdf`). Existing PostgreSQL CI targets both checks (`8eafd600`).
- Purchase-order receiving, batch/stock transaction invariants, and split hospitality stock semantics remain in their existing services. **Unverified:** new test execution, visual parity with the five approved viewport references, live POS/batch hardware and production deployment. P08/P09/P15 gates remain open.

### P06/P08/P15 actual outlet price parity — 25 October follow-on

The supermarket cashier product tile previously displayed `MenuItem.unit_price` even when the payment/order service applied `MenuItemOutlet.price_override` for that till. The existing `StaffOrderDetailView` now loads visible products' effective outlet prices using one tenant-constrained batched query, and the canonical catalogue tile displays that actual selling price on retail screens; hospitality display remains unchanged (`d3b18f9c`, `a1c37a1b`). Existing cashier integration test checks the tile and resulting transaction both use the configured override rather than the global base (`5dadb053`), with PostgreSQL CI target (`d54c9f7b`). This is a source correction; browser screenshots and tests still need confirmed execution.

### P09/P15 purchasing goods-receipt all-or-nothing boundary — 25 October continuation

- **P09 root cleanup:** The existing `receive_purchase_order_goods` service created a receipt and began posting stock before checking quantities and batch constraints across all lines. Although already inside `transaction.atomic`, failures late in a delivery required rollback and produced harder-to-reason-about partial side effects. Commit `6bbba3c8` moves positive-line, remaining ordered quantity, batch-code and duplicate-batch checks into a complete preflight before creating `PurchaseReceipt` or stock movements. Commit `e7fa777a` deletes redundant validations from the posting loop: this is not another patch or alternative receiving service. The original PO row lock, membership/outlet gate, batch receipt routines, stock ledger and duplicate delivery reference check remain intact.
- **P15 cross-phase regression:** Existing supermarket test module now covers PO with two products: over-receive on second line rejects the **entire delivery**, with zero receipt, movements or balances; a valid partial delivery posts both balances and leaves the PO `PARTIALLY_RECEIVED`; a case-insensitive repeat of the supplier delivery reference is denied without posting stock again (`bf6cb496`). This test is named in existing PostgreSQL CI (`fd07baad`).
- **Acceptance still open:** the test was committed, **not executed** in this session; live supplier-document fields, mixed cartons/batch expiry, permissions and five-width browser acceptance require evidence before declaring P09 complete. No migration, new CSS file, route, alternate controller, or schema.

### P09 carton conversion consistency — 25 October

- The existing `to_stock_units` correctly accepts a numeric whole carton such as `1.0`, but `receive_purchase_order_goods` subsequently applied `int("1.0")`, raising a late validation error despite the input having already passed conversion. `ae591cff` uses `int(Decimal(str(...)))` on the validated carton value in the original receiving service; no extra conversion function.
- The same PO receiving integration regression now posts a second delivery for the two remaining units using one supplier carton (`"cartons": "1.0"` with carton size two), confirms the PO becomes fully received, stock increases correctly and the receipt stores one carton (`8d1c1982`). Focused CI target unchanged.
- Test execution, physical receipt verification and production deployment remain **not observed**.

### Shared first-party delivery integration — 25 October 2026 (new D00–D07 workstream)

- **Product decision:** Delivery is an optional **fulfillment capability within this POS**, not a second application or financial ledger. It must serve restaurants/cafés, supermarkets/grocery/retail, bars/lounges where lawful, and hotel guest-room or external delivery using line-specific screens. Existing hospitality tables, KDS, guest folios, retail pickup, order totals, payment/stock postings and role permissions remain authoritative.
- **External references reviewed:** Shopify POS local-delivery setup and pick/pack/deliver lifecycle (2026-09-28 change; Shopify Help Center) and Toast Orders Hub first-party restaurant dispatch. Full comparison, data model, status diagram, fee/COD policy, safeguards, tenant/outlet permissions and phased acceptance are in `docs/DELIVERY_FULFILLMENT_IMPLEMENTATION_2026-10-25.md`.
- **D00 source groundwork committed** (`2f2702dc`): new `backend/apps/pos/services/delivery_policy.py` defines supported outlet types, address vs hotel-room destination validation, legal forward-only fulfillment transitions and fee input validation. The explicit first-release dispatch gate requires a settled order, assigned rider and no unresolved refund (`440ef98d`); COD does not silently activate.
- **Tests and CI:** `backend/tests/test_delivery_policy.py` validates cross-business destinations, room-only rules, stage transitions, fee bounds, and paid-only dispatch (`4f1daa1c`, `97a0381d`); existing PostgreSQL CI now runs this contract (`8ed722b9`).
- **Critical scope distinction:** D00 is **not a launched delivery feature**. D01 requires a migration-backed separate `OrderDelivery` record, per-outlet enablement and tenant checks; D02 adds paid first-party retail delivery actions; D03 restaurant/KDS, D04 hotel folio/room service, D05 bars with policy, D06 COD and financial reconciliation, D07 optional integrations. No delivery UI, new schema, payment collection or dispatch action was exposed by D00.
- **Phase coverage:** D workstreams cross-cut P03 authorization/multitenancy, P05 orders, P06 cashier, P07 settlement/refunds, P08 stock, P09 receiving/fulfillment, P10 KDS, P12 hotel, P13 tenant modules and P15 regression/viewport acceptance. D01–D07 remain not implemented and D00 unverified by passing CI.

### D01/D02 delivery persistence and staff manager queue — 25 October 2026

- **D01 schema:** `OutletDeliverySettings` (explicit per-outlet opt-in, disabled by default) and `OrderDelivery` (one existing POS order per delivery, independent fulfillment state, recipient/destination, currency/fee snapshot, worker, timestamps) added to `apps/pos/models.py`. Migrations `0030_delivery_fulfillment.py` and `0031_delivery_fulfillment_rls.py` follow the existing 0029 head and tenant-RLS pattern; no prior order, folio, pickup, payment or stock record is changed.
- **D01 service security:** `apps/pos/services/deliveries.py` authorizes only active manager membership at the actual order outlet, requires opt-in, confirmed full payment, no refunds, and mutually exclusive retail pickup; identical retries reuse the same delivery without another financial/stock posting. Hotel room delivery uses the existing *checked-in* folio/reservation room rather than arbitrary text. The existing pickup service now refuses pickup if delivery already exists.
- **D02 backend workflow:** manager-only worker assignment requires the worker's active same-tenant/outlet membership. Transition commands row-lock fulfillment, enforce legal state changes, require assigned worker + paid order at dispatch, audit changes without customer personal data, and never post another inventory or payment event.
- **D02 first UI:** new manager staff queue `/staff/pos/deliveries/` supports outlet enable/disable, eligible paid-sale selection and registration, worker assignment, fulfillment progression and privacy-scoped queue, reusing canonical staff CSS/layout. Route and manager-only navigation integrated. This is *not* COD, KDS automation, courier marketplace or third-party dispatch.
- **Tests & authorization:** `tests/test_delivery_persistence.py` covers defaults, payment/tenant/outlet role gates, duplicate fulfillment, idempotency, driver/state and hotel room; staff GET/POST manager flow and nonmanager denial. `test_postgres_rls_policy_presence.py` now requires RLS on both tables. Existing CI runs delivery policy and persistence checks on PostgreSQL and all tests on SQLite.
- **Test evidence:** previous GitHub run 40171883331 recorded successful Django system checks and `makemigrations --check --dry-run`, but its full suite was still underway when superseded by subsequent pushes; latest-run green tests are not yet observed. D01/D02 **not accepted** until passing PostgreSQL, schema deployment, manager browser flow, five approved viewports and customer payment/stock isolation are verified.
- **Related phases:** P03 tenant scope, P04 terminal authorization, P05 order identity, P07 financial separation, P08 stock ledger, P10 restaurant KDS, P12 hotel folio, P13 optional modules and P15 CI must all be regression-checked before rollout. See `docs/DELIVERY_FULFILLMENT_IMPLEMENTATION_2026-10-25.md`.

## Approved visual baseline

- **Supermarket management dashboard:** sidebar, branch/search/user top bar, greeting/banner/open POS CTA, four KPIs, setup checklist, quick actions, attention and recent activity, green/navy/white palette.
- **Supermarket cashier (two approved variants):** narrow left rail, store/cashier/register header with F3 search, broad image-product grid, top category tabs, fixed right basket with quantity buttons, prominently displayed UGX due and payment CTA, payment methods and hold/clear/print.
- **Tablet POS:** compact three-zone catalogue/basket/receipt layout only when applicable to the chosen business flow and available width.
- **Four-business unified visual:** common design language but independent supermarket, restaurant, bar, hotel dashboards and operative surfaces. No implementation is accepted merely because it resembles the image; it must work with real tenant data.
- **Reference files:** the five approved uploads from the conversation on 2026-10-23; store approved reference assets in repository design/reference after asset rights/provenance and filename approval. Until then use docs/FIZO_APPROVED_VISUAL_DESIGN_STANDARD.md and docs/FIZO_UNIFIED_UI_REFERENCE_2026-10-23.md.

## Execution phases (strict sequential gate, each with checkbox)

| Phase | Workstream | State | Exit gate |
|---|---|---|---|
| P00 | Discover and freeze baseline | In progress — [source inventory and CI baseline](evidence/p00-2026-10-23/README.md); browser baseline pending | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P01 | Architecture and CSS clean replacement | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P02 | Shared components and mobile responsiveness | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P03 | Tenant setup and true isolation | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P04 | Authentication and register identity | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P05 | Supermarket dashboard and management | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P06 | Supermarket cashier pixel-parity | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P07 | Retail transaction correctness | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P08 | Retail catalogue and stock | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P09 | Retail buying, employees, reports | ◐ Cross-phase work committed; not accepted | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P10 | Restaurant front of house | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P11 | Bar operations | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P12 | Hotel and lodging | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P13 | Mixed capabilities and optional modules | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P14 | Platform billing/admin and compliance | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P15 | Full route-by-route QA, visual acceptance, deployment | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |


### P00 — Discover and freeze baseline

Inventory routes, templates, includes, CSS, JS, API views, model writes, events, permission checks, responsive breakpoints and current screenshots. Build route-to-template-to-CSS-to-controller crosswalk; mark dead/duplicate files, gather pixel baselines. No deletions before reference and dependency analysis.

Checkpoint: source `8d45fb3` has 636 resolved URL patterns, 156 tracked templates, 28 visual candidates needing dynamic tracing and eight missing stylesheet references. Exact-source CI has 83 failing tests. See the linked P00 evidence; no phase completion or production verification is implied.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P01 — Architecture and CSS clean replacement

Enforce at most two global foundations: design-tokens.css and application-shell.css (existing fizo-fresh.css/fizo-console-shell.css can be canonical owners instead of new files). Business surface CSS only where truly distinct: retail-cashier, retail-management, hospitality, hotel-frontdesk, platform/setup, auth, printing. Merge stock/purchasing/management into coherent owner as appropriate. Delete old stylesheet only after removal of all references, exact replacement and regression validation.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P02 — Shared components and mobile responsiveness

Single canonical buttons, inputs, tables, cards, dialogs, sidebars, toasts, badges, skeletons, empty/error states, keyboard focus, screen reader behavior, printer styles; desktop/tablet/mobile/wide-screen and touch target contracts.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P03 — Tenant setup and true isolation

Tenant-aware routing, setup feature flags, module/role/permission checks enforced server side, outlet scoping, currency/timezone branding, independent menu/navigation, no hotel table artifacts on supermarket screens; tenant data access tests.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P04 — Authentication and register identity

User/password or selectable initials + PIN per configured service, lockout, invitation, recovery, assignment, safe idle behavior: retail assigned cashier should not reauthenticate frequently; restaurant/bar/hotel shared terminals auto-lock appropriately.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P05 — Supermarket dashboard and management

Match management approved reference; real UGX metrics, setup checklist, inventory/staff/purchasing quick actions, alert and activity drilldowns, branch switcher; responsive and no demo values.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P06 — Supermarket cashier pixel-parity

Match two cashier approved screenshots: header and F3 search, side nav, categories, four/five responsive product columns, image card scale, fixed basket panel, whole-item quantity, measured item fractions by unit, prominent UGX total, payment options, receipt, hold/clear/print, cashier identity, register state, customer-facing display.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P07 — Retail transaction correctness

Fast barcode scans and search; add once without unexpected refresh; product variant/UOM, offers/tax, no duplicate submission, payment cash/card/mobile money including settlement callbacks, change, void, return/refund, held/offline queue idempotency and receipts.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P08 — Retail catalogue and stock

Products, import, category, SKU/barcode, media, price lists, variants, opening stock, reorder thresholds, batches, expiration, count, transfer, receive, write-offs, scale labels, supplier links, auditable inventory ledger.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P09 — Retail buying, employees, reports

Purchasing requisition/order/receive/bills, staff setup, register shifts, cash reconciliation, all daily/monthly/export reports and owner drilldown, permissions.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P10 — Restaurant front of house

Distinct restaurant dashboard, table/floor plan, seat/guest, dine-in/takeaway, menu/modifiers/course, fire to kitchen, KDS acknowledgement and bump, split bills and combined payments, tips and service charge, receipt.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P11 — Bar operations

Bar dashboard, standalone quick sales or long-lived tab, pours/measurements, rounds, transfers, bartender shift, split tab, account settlement, discounts with approvals, stock deduction, receipt and bartender handoff.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P12 — Hotel and lodging

Hotel-specific dashboard, inventory/calendar/tape chart, rate plans and room types, availability conflict prevention, reservations, deposit, check-in, folios and payments, housekeeping, out-of-service rooms, checkout, night audit, reports.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P13 — Mixed capabilities and optional modules

Feature entitlement matrix for retail + restaurant/bar/hotel combinations: selected functions integrate cleanly but never inject irrelevant controls or alternate shells. Event bookings, room charges, customer account, loyalty and other enabled add-ons only.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P14 — Platform billing/admin and compliance

Platform tenant management, business white label, organization setup, subscription/license, audit, Uganda payments/tax/EFRIS if supported/approved, privacy, exports, backup and restore, secure integration credential handling.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P15 — Full route-by-route QA, visual acceptance, deployment

For every registered GET and POST route: navigate, screenshot compare to approved baseline, confirm actionable control, no 500, permission/tenant safety, correct currency, responsive sizes, tablet hardware, offline and printer flows. Visual diff thresholds with reviewed exceptions; Django/test/static build/lint/CI; commit to main, push, deploy and verify live health and end-to-end scenarios.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.


## Screen-family acceptance ownership

### Platform, tenant provisioning and organization console

**Template family:** `backend/apps/console/templates/`

**End-to-end owner:** Organization signup, plan, site, outlet, profile, module entitlement, setup and platform owner flows.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Public account and authentication

**Template family:** `backend/templates/`

**End-to-end owner:** Signup, password reset, login, staff invitation, approval, PIN and account recovery.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Staff shell, dashboards and common pages

**Template family:** `backend/apps/staff/templates/staff/`

**End-to-end owner:** Navigation, search, owner overview, daily management, settings, notifications, help and role-aware actions.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Retail cashier and sales

**Template family:** `backend/apps/staff/templates/staff/`

**End-to-end owner:** Register assignment, checkout, basket, price, promotion, hold/resume, customer display, shifts, receipt, return/refund, offline recovery.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Stock and inventory

**Template family:** `backend/apps/staff/templates/staff/inventory/`

**End-to-end owner:** Balances, receipts, stock counts, batch/expiry, transfer, shelf, scales, movements and reconciliations.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Purchases and suppliers

**Template family:** `backend/apps/staff/templates/staff/purchasing/`

**End-to-end owner:** Supplier records, purchase orders, receiving, payable reconciliation and returns.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Restaurant and bar table/order and KDS

**Template family:** `backend/apps/staff/templates/staff/kds/`

**End-to-end owner:** Dining tables, tabs, order rounds, modifiers, kitchen tickets, split/transfer, settle, service display.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Hotel front desk and lodging

**Template family:** `backend/apps/staff/templates/staff/lodging/`

**End-to-end owner:** Availability, rates, bookings, check-in/out, room status, folio, housekeeping, maintenance and night audit.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Events and booking

**Template family:** `backend/apps/staff/templates/staff/events/`

**End-to-end owner:** Spaces, event calendar, booking lifecycle, deposits, services, conflict detection.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Finance and reporting

**Template family:** `backend/apps/staff/templates/staff/finance/`

**End-to-end owner:** Expense/cashbook records, shift reconciliation, owner metrics and drilldown.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Customers and loyalty

**Template family:** `backend/apps/staff/templates/staff/customers/`

**End-to-end owner:** Optional retail identity, guest identity, customer data permissions and history.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Settings, staff and integrations

**Template family:** `backend/apps/staff/templates/staff/settings/`

**End-to-end owner:** Member permissions, workstation, branding, integration, EFRIS configuration, security audit.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.


## Mandatory CSS audit and disposition register

Each stylesheet below must be classified **keep as canonical / merge into shared foundation / keep as business-specific / delete after replacement**. Default state is **pending trace**; do not assume an unused name means safe to delete.

| File | Required audit | Status |
|---|---|---|
| `backend/apps/staff/static/staff/fizo-auth-2026.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-console-shell.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-fresh.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-hospitality-floor.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-hotel-frontdesk.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-inventory-workflows.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-purchasing.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-register.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-setup-area.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-setup-wizard.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-stock.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/grocery-checkout.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/grocery-owner-console.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/hospitality-console.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/hospitality-workflows.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/management-workflows.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/retail-cashier.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/retail-workflows.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/staff-kds-operations.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/staff-workbench.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |


## Exhaustive template audit register (156 tracked HTML files)

For **every** HTML entry: record named URL, base/inclusion chain, line-of-business exposure, feature flag, JS handler, CSS ownership, GET/POST handlers, model/service, permissions, expected empty/loading/errors, approved comparison screenshot(s) and responsive checks. Including a file here does **not** mean it has passed.

| Template file | Visual/function audit | Status |
|---|---|---|
| `backend/apps/console/templates/console/base.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/includes/fizo_nav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/includes/fizo_sidebar.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/includes/nav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/includes/sidebar.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/index.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/catalog_import.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_category_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_category_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_outlet_confirm_delete.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_outlet_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_outlet_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_recipe_confirm_delete.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_recipe_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_recipe_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/modifier_group_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/modifier_group_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/modifier_option_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/modifier_option_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/outlet_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/outlet_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/overview.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/practice_sale.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_rate_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_rate_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_type_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_type_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/service_offering_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/service_offering_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/service_offering_option_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/service_offering_option_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/setup_wizard.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/site_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/site_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/plan_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/plan_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/tenant_control_plane.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/tenant_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/tenant_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/base.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/business_date.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/customers/detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/customers/form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/customers/list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/dashboard.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/booking_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/booking_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/bookings_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/calendar_week.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/space_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/spaces_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/finance/category_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/finance/entries_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/finance/entry_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/documentary_photo.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/empty_state.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/exception_assessment_fields.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/fizo_pos_catalogue.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/fizo_retail_sales_landing.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/form_errors_block.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/grocery_owner_dashboard.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/messages.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/nav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/orders_lanes.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/service_tv_ticket.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/sidebar.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/workspace_subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/balances.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/batches.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/count_create.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/count_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/counts_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/intelligence.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/movement_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/movement_upload.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/movements.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/scale_labels.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/shelves.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/transfer_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/transfer_receipts.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/kds/queue.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/availability.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/folio_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/folios_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/housekeeping.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/maintenance.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/night_audit.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/reservation_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/reservation_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/reservations_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/room_types_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/rooms_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/tape_chart.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/login.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/management.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/management_shift.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/management_source.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/menu_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/notifications/inbox.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/order_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/order_detail_supermarket.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/order_print.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/orders_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pending_approval.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pin_setup.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos/customer_display.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos/offline_queue.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos/pickups.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos/wholesale_pricing.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos_shifts.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/promotion_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/promotion_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/promotions_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/purchase_order_create.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/purchase_order_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/purchase_orders_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/supplier_balances.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/supplier_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/suppliers_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/retail_pos_start.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/sales_summary.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/search/index.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/search/palette.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/service_tv.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/audit_log.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/branding.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/efris_settings.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/integration_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/integrations_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/invite_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/invites_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/member_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/members_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/modules.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/owner_reports.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/worker_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/table_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/tables_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/terminal.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/workstation_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/workstation_pair.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/workstation_test.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/workstations.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/templates/includes/phase4_control_panel.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/templates/password_reset/confirm.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/templates/password_reset/request.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/templates/public/signup.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |


## JavaScript / route owner inventory

**JavaScript sources (5):**
- [ ] `backend/apps/staff/static/staff/grocery-checkout.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.
- [ ] `backend/apps/staff/static/staff/retail-counter-v2.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.
- [ ] `backend/apps/staff/static/staff/staff-command.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.
- [ ] `backend/apps/staff/static/staff/staff-density.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.
- [ ] `backend/apps/staff/static/staff/staff-kds-live.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.

**URL inventories:**
- [ ] `backend/apps/api/urls.py` — enumerate named paths, permissions, request methods, mapped template and API dependencies.
- [ ] `backend/apps/console/urls.py` — enumerate named paths, permissions, request methods, mapped template and API dependencies.
- [ ] `backend/apps/staff/urls.py` — enumerate named paths, permissions, request methods, mapped template and API dependencies.
- [ ] `backend/config/urls.py` — enumerate named paths, permissions, request methods, mapped template and API dependencies.

**Backend dependency discovery:** map `backend/apps/*/` models, service modules, view functions, tasks, payments, signals, authorization, migrations and integration handlers to a face/flow. Backend-only modules are not ignored: security and correctness must be covered even without visible UI.

## Workflow definitions and evidence of completion

| Business | Primary happy path | Necessary exceptional paths |
|---|---|---|
| Supermarket | Assigned cashier → open register → barcode/search → instant basket → payment → receipt → next sale | Unrecognized barcode, measured goods, out-of-stock policy, duplicate scan/submit, hold/resume, refund, offline queue, printer failure, closing balance |
| Restaurant | Shift → floor/table → items/modifiers → kitchen → serve → split/pay → close table | Transfer table, void approval, round sequencing, printer/KDS outage, split by seat, partial payment |
| Bar | Bartender PIN → new tab/quick sale → drinks/rounds → settle/transfer → shift close | Running tab, suspended tab, cash/card/money split, wastage, overpour/stock, return and manager override |
| Hotel | Availability → quote/rate → reserve → assign room → check in → post folio → housekeeping → pay/check out → night audit | Date collision, out-of-service room, change room/rate, deposit and refund, late/early stays, partial folio and reversal |
| Platform | Signup → business choice/modules → branch/register/staff/product/room/menu setup → test transaction → activate | Module downgrade, out-of-entitlement route, tenant crossover, broken setup step, password/PIN recovery, currency mismatch |

## Exact implementation procedure for each face/defect

1. Capture current UI and approved target, including exact viewport and state.
2. Trace actual route → view → template + includes → CSS and JS → persistence; write one root-cause statement.
3. Identify canonical component and stylesheet owner, then modify original owner in place; remove old selector/controller/template code, not override it from another layer.
4. Cover all server behavior including failure, permissions, money formatting, rounding, race conditions and transactions.
5. Test keyboard, touchscreen, scanner, printer, accessibility and different sizes. Compare target pixel geometry; iterate in same canonical owner.
6. Search repository for stale imports, selectors, duplicate listeners and old functions; delete only with proof that no live route depends on them.
7. Run focused and cross-business regression, then push direct `main` commit. Attach SHA and browser/CI evidence; update the corresponding row to completed **only after** release verification.

## Technical acceptance gates

- **CSS:** one or two shared foundations only, no unowned selector overlap; no blanket `!important`, dead files removed, no inline style-as-patch and no double-loaded assets; verified browser computed styles.
- **Data:** currency comes from tenant setup (UGX for Fizo Tech), monetary arithmetic uses Decimal, payment retries idempotent, stock changes traceable, shift/customer identity and tenant scope correct.
- **Business boundaries:** server blocks unauthorized line-specific routes and API methods; screen hides unavailable modules; retail needs no table/guest name; mixed entitlements show only enabled features.
- **Operational quality:** no random refresh while adding items, whole quantities for unit items, fractional quantities only for configured measures, one working search/scanner controller, real register identity, accessible receipt and customer display, quick return to next sale.
- **QA:** view/layout screenshot diffs for all templates, Django checks, migrations check, static compilation, tests, CI, live smoke flows on Fizo tenant and independent hotel/restaurant/bar tenants; a browser screenshot is required for any pixel-perfect claim.

## Progress accounting

Maintain one row per phase and one per template/CSS file. Use states `not started`, `in progress`, `implemented awaiting browser validation`, `verified on staging`, `verified in production`. Count only production-verified items in completion percentage. Record defects with root cause, canonical replacement, removed files/functions, and evidence; do not relabel source code written as feature done.

## Research anchors

- Oracle Simphony transaction and KDS operations: https://docs.oracle.com/en/industries/food-beverage/simphony/
- Oracle Simphony staff/check/order flow: https://docs.oracle.com/cd/E76065_01/doc.29/e69878/
- Cloudbeds PMS daily hotel workflow: https://myfrontdesk.cloudbeds.com/hc/en-us/articles/40771665486363-Your-Cloudbeds-PMS-Daily-Operations-Guide
- Existing repository: docs/FIZO_POS_EIGHT_PRODUCT_BENCHMARK_2026-10-22.md, docs/FIZO_FULL_ROUTE_TEMPLATE_MASTER_2026-10-22.md, docs/FIZO_ROUTE_VERIFICATION_REGISTER_2026-10-22.md and line-specific acceptance registers.

**Authority:** This document is the umbrella implementation contract. Existing acceptance registers provide details, but no earlier checklist can waive the canonical-owner, full-route, isolation, visual-parity or no-patching rules above.
