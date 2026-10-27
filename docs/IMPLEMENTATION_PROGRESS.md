# Bar–Hotel–Retail suite — live implementation progress board

**Last reviewed:** 16 October 2026  
**Authoritative acceptance and chronological evidence:** [Full 34-phase checklist](SUITE_IMPLEMENTATION_TODO.md)  
**Required supermarket workstream:** [Supermarket checklist — 36 capabilities](SUPERMARKET_IMPLEMENTATION_CHECKLIST.md)
**Retail depth execution plan:** [Retail expansion roadmap — QuickBooks-depth benchmark](RETAIL_EXPANSION_ROADMAP_2026-10-27.md)

This is the practical progress index, **not a claim of production certification**. Mark `[x]` only when the complete named workflow is implemented and local verification is recorded. `[-]` means meaningful functionality exists but missing acceptance tasks remain. `[ ]` means untouched.

## Suite milestone summary

| Status | Count | Interpretation |
|---|---:|---|
| [x] Implemented and locally verified | **4 / 34** | Phases 01–04, subject to separate real-browser/PostgreSQL/hardware gates |
| [-] In progress | **30 / 34** | Real code in place, incomplete scope or acceptance |
| [ ] Untouched | **0 / 34** | All phases have been started; **starting is not completing** |
| External release certification | **Not yet complete** | Do not market as fully certified/production-ready based on SQLite CI alone |

**Code-evidence supermarket baseline:** 10 existing, 13 partial, 13 planned. All 36 require scoped production acceptance as defined in their tracker.

## Phase-by-phase tracker

| Phase | State | Purpose / existing footing | Remaining highest-value work | Supermarket IDs |
|---|---|---|---|---|
| 01 Workstations/registers | [x] | Named tills and per-register attribution | Hardware/multi-till trials | SM-07 |
| 02 Role workspaces | [x] | Cashier, storekeeper, manager and hotel destinations | Fast cashier UX/browser verification | SM-11, SM-33 |
| 03 Manager exception centre | [x] | Scoped exceptions, reviews, thresholds | Retail fraud analytics and real action approvals | SM-35, SM-20 |
| 04 Shift handover | [x] | Counted cash, variances, manager handoff | Real till reconciliation drills | SM-07 |
| 05 Unified customers/guests | [-] | Tenant-scoped profiles, guest/order/event links, merges, financial summary, read-only API work | Exact-head CI for new API/finance/UI; customer acceptance, privacy and PostgreSQL/browser evidence | SM-22, SM-23 |
| 06 Loyalty/accounts | [-] | Points earning, refund reversal, ledger and staff review | Redemptions, coupons, tiers, benefit rules and liability policy | SM-22, SM-30 |
| 07 Inventory intelligence | [-] | Planning views, movement analysis, filtered CSV export; package conversion through checkout/PO receiving; retail assembly BOM with atomic build/unbuild stock runs | Reorder lead times, costing, counting, supplier-specific pack costing, lot-aware assembly handling and concurrency/browser acceptance | SM-08, SM-17, SM-19, SM-26 |
| 08 Batch/expiry/FEFO | [-] | Batch visibility, holds and waste | Atomic FEFO, recalls, expiry sale-block and legacy handling | SM-09, SM-18 |
| 09 Purchasing journey | [-] | PO, receiving, supplier exposure | Requisition, quote comparison, 3-way match, credits, vendor lead time | SM-10, SM-16, SM-31, SM-36 |
| 10 Business date | [-] | Business-day/timezone infrastructure | Consistent boundaries in all reports, shifts and DST tests | SM-29 |
| 11 Hotel night audit | [-] | Nightly folio operations | Full property close and reconciliation | — |
| 12 Housekeeping | [-] | Housekeeping board and staff actions | Mobile and cross-role real workflow certification | — |
| 13 Kitchen display | [-] | KDS state/service UI | Routing and device-level timing/interaction evidence | — |
| 14 Events journey | [-] | Bookings, quotes, payments | Full package, settlement and invoice workflow | — |
| 15 Hardware | [-] | Workstation configuration, receipt/scanner hooks, outlet-scoped shelf-label PDF output | Physical barcode/shelf-label printer alignment, scale and customer-display adapters | SM-03, SM-12, SM-15, SM-28 |
| 16 Offline | [-] | Offline queue, replay and conflict basics | Retail till offline safety policy and privacy | SM-21 |
| 17 EFRIS | [-] | Fiscal outbox, status and bounded retries | Provider-certified format, reference checks and URA sandbox proof | SM-13 |
| 18 Analytics | [-] | Sales overview, management reports | Real cost/margin, shift drilldowns, supplier and basket analytics | SM-19, SM-29, SM-35 |
| 19 Scheduled reports | [-] | Daily/weekly/monthly email reports | Delivery diagnostics and calendar/provider proof | SM-29 |
| 20 Capability permissions | [-] | Inventory/purchasing capability policy | Consistent POS/finance/hotel API-service checks | SM-20 |
| 21 Manager approvals | [-] | Transaction-bound manager PIN approval service with exact intent hash, enforced different approver, outlet scope, expiry, replay safety and evidence; retail refunds, line discounts, full-basket voids, cash payouts and manual stock write-offs wired | Finish remaining sensitive paths (notably line-level void and any future reopen/cashier price-override workflow), service/API parity, and deployed manager-till acceptance | SM-20, SM-35 |
| 22 Owner audit | [-] | Event/review histories | Retail price overrides and source-to-document export | SM-35 |
| 23 UI density | [-] | Responsive themes/touch and dense layouts | Scan-first cashier, tablet and keyboard evidence | SM-11, SM-33 |
| 24 Command palette | [-] | Command search/shortcuts | Staff scope/accessibility and entity completion | SM-33 |
| 25 Global search | [-] | Scoped lookup foundations | All products/SKUs/receipts/suppliers and fast pagination | SM-14, SM-32 |
| 26 Notifications | [-] | Staff notification surfaces | Cash variance, stock/expiry and supply alerts | SM-18, SM-35 |
| 27 Onboarding | [-] | Business-type/configuration setup | Large catalog import, staff scanner training, outlet setup | SM-14, SM-34 |
| 28 Demo/training | [-] | Guarded local training tenant seed | Guided UI, reset, simulated transactions and explicit banner | SM-34 |
| 29 Subscription entitlements | [-] | Plan/module overlays and owner choice | Limits, lifecycle and parity with API/services | SM-01, SM-34 |
| 30 Documentation/feature matrix | [-] | Roadmap and audit baseline | Verified UI/backend/API/DB/hardware capability register | All |
| 31 Release certification | [-] | Some CI and validation commands | Real PostgreSQL, browser, hardware, worker and restore evidence | All |
| 32 Financial/historical policy | [-] | Read-only historical posting audits | Formal correction, split-tender tax/refund controls | SM-06, SM-13, SM-23 |
| 33 Deployment/operations | [-] | Preflight and runbooks | Restore drill, worker probes, migration and rollback proof | SM-34 |
| 34 Commercial source policy | [-] | Policy research/documentation | Owner-approved source/license/distribution decision | — |

## How to finish rather than just start a phase

1. Select one phase and its linked supermarket IDs. Inspect the existing code and avoid parallel implementations.
2. Write the **acceptance journey** (cashier, manager, storekeeper, owner, customer where appropriate) including permission denials, mobile/desktop layouts and failure/retry states.
3. Complete backend + screen + navigation + service/API + audit and migrations as one work item.
4. Add named tests for the journey and record the exact commit with full green CI; fix failures before starting a new batch.
5. Record PostgreSQL/RLS, concurrent workers, browser widths, hardware/URA evidence **separately**. Missing external evidence must remain visible, not hidden under a green checkbox.
6. Update this board, the parent phase, and the supermarket SM rows; report the remaining scope and actual verified progress, never percentages based on source commits alone.

## Next delivery queue

**1. Finish Phase 05** customer identity and scoped finance/API acceptance.  
**2. Priority-zero supermarket operations** (SM-P0.1 through SM-P0.6), particularly a dedicated fast scan-to-checkout lane and safe catalog import. These should be developed as part of phases 02/07/15/23/27, without reopening proven implementation unnecessarily.  
**3. Finish Phase 09** purchasing and receiving integrity.  
**4. Finish Phase 08** batch/FEFO/recall and **Phase 07** replenishment/counting.  
**5. Finish Phase 06** loyalty and promotions once money and return calculations are reliable.

This order explicitly elevates supermarket fundamentals ahead of nice-to-have analytics while retaining the agreed customer, purchasing and stock dependency order.

## Exact-commit verification ledger

| Date | Commit | Result | Interpretation |
|---|---|---|---|
| 2026-10-16 | `615b20e66ddf` | 492 tests passed, 5 skipped on GitHub Actions | Historical SQLite baseline; no browser/hardware certification |
| 2026-10-16 | `067238531317` | 532 passed, **2 failed**, 5 skipped | Customer duplicate form non-field errors not displayed; later code fixes were committed |
| 2026-10-16 | Later customer/API and supermarket documentation commits | Await latest exact-head CI check | Do not assert a green result before GitHub Actions reports success |

Refresh this ledger from actual GitHub Actions evidence with every delivery checkpoint. Do not silently overwrite the last failed result.

## Supermarket delivery log — 2026-10-16

- **SM-P0.1 cashier lane, first code slice:** supermarket order details now provide a scan-focused form, barcode shortcut, client-side duplicate-submit suppression, live status text and POST-only next-customer creation. Reuses existing order, scan validation and till/payment code. Regression tests added in `backend/tests/test_supermarket_cashier_lane.py`.
- **Verification:** new commit requires full CI; no real-scanner, concurrent till, browser/mobile or payment provider sign-off is claimed. SM-11 and SM-P0.1 are not yet complete.
- **Next:** finish the scan-to-payment workflow, then SM-P0.2 catalog import and SKU integrity, SM-P0.3 tax/refund correctness.

## Supermarket delivery log — catalog import expansion, 2026-10-16

- Began **SM-P0.2** by strengthening the existing protected owner CSV importer, **not** building a second ingestion path. Bounded one-transaction import limit increased from 250 to 1,000 products/1 MB; CSV preview, case-insensitive duplicate SKU/barcode rejection, tenant-scoped writes, and atomic rollback remain.
- Added test coverage for a successful 300-item batch plus updated max-row rejection boundary. This batch **does not update existing products** or insert stock balances, so opening stock must still be received via the inventory ledger.
- Research baseline: Shopify's official product CSV guide recommends small test batches, strict CSV formatting and explicit overwrite semantics; all three inform the safe create-only policy until verified update rules are implemented.
- **SM-P0.2 is not complete:** stable upsert/price-change approvals, 1,000-row UI and performance checks, cross-branch product assignments, precise import history and production PostgreSQL/browser acceptance remain.
- CI status must be recorded for the **exact head commit**, not from a superseded cancelled run.

## 2026-10-16 — SM-P0.2 catalog operations delivery

- Raised create-only CSV import to **1,000 items / 1 MB** and preserved preview, tenant isolation, SKU/barcode duplication checks, atomicity, and separation of stock from item definitions.
- Added tenant-scoped owner export of catalog fields and protected spreadsheet text; rejects malformed/truncated input rather than silently creating incomplete records.
- Added owner-accessible **Bulk base price updates** on the existing Catalog import page: download a current price sheet, edit `new_price`, preview, re-upload and apply. SKU and `old_price` must match current data; ambiguous duplicate SKUs or stale values reject the whole batch. One atomic transaction updates prices and writes a before/after audit event without rewriting receipts or stock.
- Added regression tests for large batches, malformed CSV, protected export, stale and cross-tenant price rows, duplicate SKUs, unchanged stock, and auditable price changes. **Exact-head CI is not yet certified** and production PostgreSQL/browser/data-volume tests remain required.
- Baseline research: Shopify official guidance on CSV overwrite risks and test imports, plus Odoo official barcode and item configuration references. No automatic cost/stock edits or product deletions were introduced.


### 2026-10-16 — F3 reviewed stock counts (software checkpoint)

- Reused the existing count sessions and stock ledger. Storekeepers record physical quantities, skip uncounted items, and submit immutable audit snapshots for a different manager to approve or return with a reason. Posting rejects changed or net-zero-moved stock instead of overwriting intervening sales, receipts or transfers. A separate approval queue is accessible through the inventory UI and API.
- The existing direct completion domain service is now manager-only, with a regression test proving an authorized storekeeper cannot bypass approval. No duplicate stock ledger or new sale/customer/table dependency was introduced.
- Exact prior green source checkpoint: ed449b03359a0a2f2f2a0062c94bad3f46494a46 — https://github.com/birleopold/Bar-Hotel-POS/actions/runs/38956165341 — 592 passed, 5 skipped, 20 subtests; Django checks and migration-drift checks passed. This final permission guard/documentation commit requires its own CI.
- F3, Phase 07 and Phase 08 stay IN PROGRESS: carton/unit conversions, in-transit transfers, original-lot reconciliation, PostgreSQL two-till races, mobile/browser workflows and physical devices remain unverified.


### F3 carton-to-unit conversion — 17 October 2026

- Tenant product configuration now provides **pieces per carton** for tracked pieces (1 = disabled). Purchase orders accept whole cartons alongside loose units and retain their **original carton size snapshot**. Supplier receiving uses that snapshot, stores the quantity of cartons entered, rejects duplicate delivery references, and posts only base-unit quantities to the existing stock ledger. Supplier cost remains per individual piece.
- Staff/API stock transfers and staff physical counts accept cartons plus loose units through one bounded, finite and precision-checked converter. Ordinary POS checkout and historical stock quantities are unchanged; legacy purchase orders have a safe carton factor of 1.
- Research: Odoo 19 official [Units of measure](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/product_management/configure/uom.html) and [Packaging](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/product_management/configure/packaging.html). This implementation is **not F3 completion**; multi-stage transfer dispatch/acceptance, real PostgreSQL concurrency, browser/device acceptance and lot reconciliation remain open.


### F4 invoice-linked supplier settlement implementation — 17 October 2026

- Extended the existing PO payment model with an **optional verified invoice link**; historical PO-wide payments are preserved, not redistributed. Backend checks prohibit paying more than received value, net invoiced PO balance or the selected invoice's outstanding amount. Idempotency identity now includes invoice ID. Supplier credits cannot exceed the individual invoice's unpaid value after allocated payments.
- PO staff UI shows invoice-level payment, credit, unpaid and overdue figures; requires explicit invoice choice for newly entered payments when bills are present. Unassigned historic payments trigger a reconciliation warning and block further invoice-specific settlements in the staff UI. Invoiceless receipt-backed payments remain available.
- Existing purchase-order API returns linked payment references and invoice-level balances, with null/unverified exact balances when historical PO payments remain unallocated. Added regression tests for the invoice-specific money limit, linked retry, cross-PO access, credits and legacy data. This work is **F4 in progress**, not full three-way item/price matching, physical vendor returns, PostgreSQL or browser certification.


### F4 purchasing financial and goods reconciliation — 17 October 2026

- **Code-implemented:** invoice line-level three-way matching checks original purchase-order unit price and actual accepted receipt quantities, subtracts physical supplier returns and previously invoiced quantities, and verifies the exact invoice total. Each matched line is recorded immutably; historical header-only invoices remain explicitly labelled unmatched rather than misrepresented as verified. Existing API input without lines is retained for legacy compatibility, while the staff create flow requires actual invoice line inputs.
- **Code-implemented:** original delivery-line supplier returns deduct exactly the physically returned quantities from available inventory with one audited stock movement and batch-specific allocations. Replays do not double-count; overreturns, insufficient balance, missing original batch and inaccessible outlet/role are rejected. Supplier credit notes and cash repayment remain separate, explicit financial workflows; receipts and payments are never silently reversed. Received-goods settlement ceilings use net returned quantities.
- **Software F4 purchasing journey delivered:** suppliers, PO creation, partial / batch-aware receiving, original costs, document-level and line-level invoice matching, credit notes, invoice-specific settlement, manager reconciliation of historical payments, supplier returns, scoped staff and REST actions. Remaining **field acceptance**: independent PostgreSQL concurrency/RLS deployment exercise, real supplier invoices and returns, accounting/URA treatment of fees/taxes, browser/mobile acceptance and reconciliation of historical unmatched bills. No production certification claimed.
- **F5 started:** manager shift investigation now exposes explicitly linked tender totals per original method and currency, refunds, counted versus expected cash, handover state and order drill-down. Older time-window-attributed shifts warn that the linked-only result is not a complete reconciliation.
- Research references: [Microsoft three-way matching](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching); [Shopify supplier receipts and returns](https://help.shopify.com/en/manual/inventory-and-locations/purchase-orders/creating-inventory-transfers). Do not silently apply other-country tax assumptions.


### F6 — supermarket optional workflows and safeguards (software implementation, 18 October 2026)

**Delivered in code, awaiting exact-SHA CI/acceptance:**
- **SM-32 shelf locator:** An outlet-scoped, read-only-inventory aisle/shelf/bin lookup using existing stock balances; staff can search SKU, name, barcode or picking address, and authorized inventory roles can assign a location without modifying stock. Includes REST lookup/update, tenant/outlet controls, audit event and PostgreSQL row security. This is a location *label* per SKU per section, not a second bin-quantity ledger, transfer or full path optimization.
- **SM-12 weighed barcode subset:** Extended existing SupermarketSkuProfile with optional and uniqueness-guarded local EAN-13 weight rules: prefix 20–29 + five-digit product + five-digit **net grams** + check digit. Explicit owner/administrator configuration is accessible at Inventory → Scale labels for eligible kilogram SKUs. Scanning calculates kilograms server-side, uses original retail pricing/tax and forbids multiplying an already-weighed label. Bad checksum, zero weight, missing authorization and duplicate mappings fail closed. Does **not** claim all GS1/national layouts, tare hardware, embedded-price formats or certified weighing-scale/printer integration.
- **SM-21 offline cash safety:** Reused the existing offline queue and conflict-review page. Owners can optionally set a per-payment cash ceiling in the tenant's default currency; actual replay checks the limit and rejects cross-currency guesses and over-limit tenders. Electronic tenders remain online-only and existing request-id replay protection is preserved. Blank ceiling preserves historical tenants; a limit does not guarantee unsent local data, cached prices or concurrent offline stock availability.
- Staff pages use the existing mobile table wrapping, search, explicit form labels, visible status/errors, touch-sized actions, role scoping and existing tenant/navigation patterns. Software regression tests cover replays, cross-tenant/outlet access, weight-check digit, ownership, stock conservation, offline cash ceilings and staff forms.

**Still OPEN for F6 / cannot claim completed:** SM-22 points redemption and valuation/consent, SM-23 retail credit accounts/aged receivables, SM-24 layaway/deposits/pickup and cancellation, SM-25 wholesale price lists, SM-28 paired customer display, SM-35 loss prevention, and hardware-specific scale/tare, price-encoded labels, printer/scanner, desktop/tablet/mobile browser and offline sync device trials. F5 manager controls are not bypassed or automatically marked complete. These items stay on the original checklist, not silently waived.

**Research/design:** GS1 General Specifications (variable-measure restricted circulation prefixes and country-specific encodings) https://ref.gs1.org/standards/genspecs/15.0.0/ ; W3C WCAG 2.2 target-size minimum https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum ; Shopify offline checkout payment/device risk https://help.shopify.com/en/manual/sell-in-person/shopify-pos/selling-offline/offline-checkout . Uganda/regional scale formats must be validated with actual local equipment; no universal mapping assumption.


### F6 store-specific pilot checkpoint — 18 October 2026

**New verified-in-code workflows:** manager-maintained wholesale quantity tiers and approved, identified-customer line-price snapshots (normal anonymous shelf prices unchanged); original-line quantity tier recalculation, strict no-promotion stacking and immutable price audit; authenticated read-only no-PII customer second-screen basket/tender snapshot, responsive and no-store cached; owner-authorized non-cash loyalty reward redemption using locked points ledger, same-key replay protection and no invented points-to-money value; paid sale pickup scheduling, retailer-scoped pickup queue and single handover confirmation with *no second stock or financial posting*. Existing F6 shelf/bin lookup, configured EAN-13 scale labels, offline payment limits and replay protection remain delivered.

**Guardrails and explicit unavailable workflows:** customers can still use anonymous supermarket sales with no name or room/table. Retail credit accounts/credit-sale AR and *unpaid layaway with deposits/reservations/cancellations* are **not enabled**: the current payment-finance cashbook recognizes POS receipts immediately and does not provide the accrual receivable/deposit-liability ledger, credit write-offs and reserved-inventory allocation those promises require. A fully paid pickup must not be marketed as layaway. Customer-facing second-screen is staff-session authenticated, not publicly paired hardware. Redemption is non-cash only. Approved retail hardware/scale, tax and receipt certification, real PostgreSQL/RLS concurrency, multi-device browser/accessible scanner tests and backup/rollback remain acceptance tasks, **not certified by CI**.

**Delivery truth:** F6 is *software-in-progress* for SM-23/24/25/28/34/35; the new F6 subworkflows are code-delivered with automated regression checks. This is not a claim that the full batch is fully completed or approved for rollout. The parent 34-phase roadmap remains in force. See `docs/SUPERMARKET_F6_ACCEPTANCE.md`.


### Retail cashier lifecycle + approved UI alignment checkpoint — 25 October 2026

**Code delivered on `main`:** asynchronous product/barcode additions now reconcile the existing basket without unnecessary page navigation, including first-item activation of the server-rendered payment controls; quantity changes update basket totals inline; ambiguous POST confirmations offer read-only reload rather than replaying a financial or stock mutation. Part-paid baskets can be held/resumed without discarding payment history. Quantity reductions that would create an overpayment report the exact supervisor-approved refund required before the reduction can proceed. Refund and item-refund forms now carry stable rendered idempotency identities. Full-basket cancellation remains blocked until all recorded payments are reconciled by refunds, audits the final payment/refund/net state, and does not create inventory restock movement for an open sale that never consumed stock.

**Approved cashier UI alignment:** retained the single compact register header and two-pane supermarket workflow; header order is store identity → product/barcode search → register → signed-in cashier → customer-display icon. Desktop catalogue remains a five-column visual product grid with horizontal categories and a persistent right-side basket/payment panel. Product cards were reduced by roughly ten percent to fit more of the primary checkout in one desktop viewport. The basket summary now uses explicit Subtotal / Discount / Tax / Total due rows with named selectors so asynchronous quantity changes cannot depend on row position. The live cashier rail is reduced to the approved operational navigation, labels retail analytics as Reports, and now includes a functional Help link at the bottom beside terminal locking. Navigation/header height, category spacing, basket rows and thumbnails were tightened; category tiles now use the approved soft pastel treatment while active selection remains green. Cashier CSS cache-buster is now `20261025.6` and checkout JS is `20261025.3` so deployed browsers do not keep older malformed assets.

**Verification truth:** source-level regression checks and JavaScript syntax checks were performed for these changes. The available TinyFish browser profile is not currently recorded as authenticated to the POS, and this session has not completed an authenticated live pixel-by-pixel browser comparison, a full Django test suite, or production deployment certification. Those acceptance gates remain OPEN; do not mark the cashier or P3/P4 complete solely from these source changes.


### F5 manager register reconciliation checkpoint — 25 October 2026

**Implemented in code, awaiting browser validation:** the existing canonical management register-shift review now exposes the physical drawer calculation (opening float, cash sales, cash refunds, float added, drops, payouts and expected cash), counted cash and variance, shift-linked tender totals by method/currency, drawer movement history, payment/refund receipt drill-down and handover evidence. The cashier Register Shifts history links managers to this existing management review; no parallel shift-detail route or duplicate ledger was retained. Legacy shifts remain explicitly labelled as incomplete linked-attribution evidence.

**Checkout reliability repaired in the same pass:** dynamically inserted payment forms and cash panels now bind independently, preventing the already-bound payment form from skipping a newly rendered cash calculator after first-item activation. The quantity summary script no longer contains a literal escaped newline and now keeps Subtotal / Discount / Tax metadata synchronized.

**Research anchor:** current Square cash-drawer guidance exposes starting cash, cash payments/refunds, paid-in/out events, expected cash, counted cash and per-shift event history. The implementation follows that evidence model while using this project's existing `PosShift`, `CashDrawerMovement`, `Payment`, `Refund` and handover records rather than introducing another accounting store.

**Acceptance truth:** source/template regression checks were added and the checkout inline JavaScript parses successfully. The saved TinyFish profile has no recorded POS sign-in, so authenticated live browser/touch/scanner validation and pixel comparison remain OPEN. F5 is still in progress; promotion/void exception handling already lives in the existing Management → Exceptions workflow and should be connected/reused rather than duplicated.


### Retail terminal-session and cancellation UX checkpoint — 25 October 2026

- **Live browser finding:** with TinyFish explicitly forbidden from touching Lock terminal/authentication controls, the saved session successfully reached authenticated management/register pages. A later direct navigation to `/staff/pos/checkout/` redirected to the PIN terminal without TinyFish pressing Lock. The server policy was therefore part of the failure, not only browser automation.
- **Root cause corrected in source:** PIN sessions default to the hospitality/shared-terminal two-minute idle window; retail previously received only a 15-minute extension and could fall back to two minutes in a mixed workspace before an outlet was resolved. Verified supermarket/retail registers now use an eight-hour shift-length idle window, and the retail checkout route can establish that policy from an authorized accessible retail outlet before a selection is persisted. Manual Lock terminal remains immediate; non-retail/shared-terminal behavior keeps the short policy.
- **Regression coverage:** a retail PIN session several minutes idle remains authenticated, and mixed retail/hospitality workspaces entering the retail checkout receive the retail shift-length policy. Existing stale-session invalidation remains in force.
- **Cancellation UX:** DRF validation containers are flattened to human-readable messages. Refund-before-cancel now recognizes nested/list `refund_required` codes and never intentionally renders `ErrorDetail(...)` representations to the cashier. The financial safeguard is unchanged: recorded payments must still be refunded/reconciled before a part-paid basket can be cancelled.
- **Acceptance status:** implemented on `main`, awaiting deployment and a repeat TinyFish checkout test. Do not mark live checkout authentication or pixel parity verified until that deployed retest succeeds.


### Retail cashier startup simplification — 25 October 2026

**Implemented in source, awaiting CI/deployed browser acceptance.** The supermarket/retail daily start path is reduced from workspace/outlet/workstation/shift navigation to a cashier-first flow:

1. Account sign-in for a cashier or PIN on an established counter terminal.
2. Retail cashier/PIN sessions land directly at `staff-retail-pos-entry`; password-authenticated managers keep the management dashboard unless they explicitly entered checkout.
3. The checkout entry silently reuses the authorized outlet, existing selected till and the cashier's one live till shift where it can do so safely.
4. If exactly one usable till exists it is remembered automatically. If no physical workstation is configured, small stores use the existing section-wide register model and see no workstation setup.
5. Only when multiple usable tills are genuinely ambiguous does the same start screen ask “Which till are you using?”
6. If no shift is open, the same screen asks only for **Cash in drawer now**. Pressing **Start selling** atomically opens the shift and creates/reuses the cashier's first active basket, with tenant serialization preventing a double tap from creating duplicate empty baskets.
7. If a shift is already open, opening-cash input disappears; **Start selling** enters checkout. The cashier start page no longer exposes daily “Shift and drawer” or “Register devices” navigation. Held sales remains directly reachable.
8. Retail PIN copy now says **Start selling / Continue to checkout** instead of shared-workspace terminology. Hospitality/shared-terminal wording and short idle policy remain separate.

This keeps opening-float reconciliation because established retail POS products use it to make expected-vs-counted drawer close meaningful, while hiding register administration from routine cashier work. Current reference patterns checked: Lightspeed Retail opening shifts, StoreConnect shift start, and other current retail register guidance all use cashier/PIN + opening float + direct POS entry rather than separate technical setup pages.

Regression coverage added for direct retail PIN landing, cashier password landing, manager password dashboard preservation, one-action shift+first-basket creation, multi-till same-screen choice, shift-length retail PIN idle behavior and simplified template language. **Do not mark browser verified until the new head is deployed and TinyFish reaches the product grid without navigating through shift/workstation administration.**


### 2026-10-26 — roadmap reconciliation checkpoint

- Current main has advanced Phase 21 beyond role eligibility: transaction-bound approval evidence exists and is visible in the manager workspace; retail refund and line-discount flows enforce manager PIN approval with exact intent, scope, expiry and replay protection. Phase 21 remains **in progress** because not every named sensitive action is wired through the same boundary and field acceptance is incomplete.
- Phase 15 now includes a software shelf-label workflow using existing catalog/barcode data and outlet prices. Hardware certification remains open, so the phase stays **in progress**.
- Retail line discount is now included in the cashier no-refresh workstream. This does not imply refunds, returns, voids, holds/resume or all approval actions have been converted to same-screen asynchronous flows.


### 2026-10-26 — Phase 21 approval boundary expansion

- Enforced segregation of duties centrally: the requester is excluded from eligible approvers and the authorization service rejects self-approval even if a manager's own PIN is supplied.
- Retail full-basket void now allows a cashier to request a different manager's PIN approval. The exact order totals, active line count and reason are bound to the approval before cancellation; part-paid baskets still require separately audited refunds first.
- Cash drawer payouts now require a second manager approval bound to the shift, workstation, amount and reason. Float additions and safe drops keep their existing workflow.
- Manual inventory adjust-out and waste now require a transaction-bound manager approval and one-time request identity. Replays do not deduct stock twice. CSV uploads reject negative adjustment rows so bulk import cannot bypass the approval boundary.
- No generic cancelled-sale reopen flow exists in the current product, and outlet price override is currently catalog configuration rather than a cashier override action. Those names remain policy placeholders rather than falsely claimed completed workflows.
- Phase 21 remains **in progress** until the remaining applicable sensitive actions, API/service parity, deployed browser/PIN acceptance and production-style concurrency evidence are complete.
