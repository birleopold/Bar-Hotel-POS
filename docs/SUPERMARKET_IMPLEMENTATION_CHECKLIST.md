# Supermarket and retail POS — implementation and acceptance tracker

**Parent roadmap:** [34-phase suite roadmap](SUITE_IMPLEMENTATION_TODO.md)  
**Scope:** independent Ugandan supermarket, grocery shop, retail counter, wholesaler and mixed retail outlet, without hotel/bar branding when those modules are disabled.  
**Status date:** 16 October 2026. **This is a code-evidence assessment, not a claim of hardware or production certification.**

## Read this before changing a checkbox

- **[x] Existing working foundation (code-evidenced):** a corresponding model/service and staff path exist; tests and external acceptance may be partial, so the broader end-to-end workflow must still meet its linked delivery item. It still needs the release's PostgreSQL/browser/hardware acceptance separately. Do not infer all edge cases are solved.
- **[-] Exists but needs completion:** some working code/screens exist, but a core end-user step, reconciliation path, authorization or acceptance evidence is missing.
- **[ ] Not implemented or not evidenced:** do not advertise the feature. If code is discovered later, inspect it and update status with evidence instead of building a duplicate.
- Each ID is stable. A phase is complete only when its **Definition of Done**, functional tests and user-facing workflows pass. Record exact-commit CI and external certification separately.
- This file is **the supermarket delivery backlog**, not a replacement for phases 01–34. Link each improvement back to the original phase. Keep hotel/bar/restaurant modules independent of the retail offering.

## Current supermarket capability assessment

| ID | Status | Capability | Evidence already in repository | What's still needed / boundary | Parent phase |
|---|---|---|---|---|---|
| SM-01 | [x] | Retail/supermarket business type and independently configured outlet | `apps.tenants.business_lines`, `OutletType.RETAIL/SUPERMARKET`, module resolution | End-to-end no-hotel branding/browser audit | 27, 29 |
| SM-02 | [x] | Product catalog with SKU, barcode, unit price, tax rate, active state | `apps.catalog.models.MenuItem` and staff catalog | Complete retail import/catalog UX in SM-14 | 27 |
| SM-03 | [x] | Scan/enter barcode or PLU into open sale | `order_detail_supermarket.html`, POS scan-add service | Physical scanner speed, duplicate-scan, keyboard focus testing | 15, 23 |
| SM-04 | [x] | Per-line quantities including weight/UoM | `MenuItem.unit_of_measure`, supermarket pricing/line services | Certified scale integration and weighed barcode formats in SM-12 | 15 |
| SM-05 | [x] | Item-level discounts and auditable promotions | retail order template, POS promotion/discount services | Complete manager PIN + promotion stacking policy in SM-20 | 06, 21 |
| SM-06 | [x] | Recorded physical returns and linked partial refunds | `SupermarketLineReturn`, refund/return services and staff page | Exchange workflow, discount/tax allocation and stock disposition testing | 04, 32 |
| SM-07 | [x] | Workstations, cashier shifts, drawer reconciliation and handover | `Workstation`, `PosShift`, shift-handover/shift close staff screens | Real multi-till device concurrency and cash tests | 01, 04 |
| SM-08 | [x] | Stock balances, transfers, counts and adjustments | inventory views and shared stock services | More ergonomic handheld cycle counts in SM-17 | 07, 20 |
| SM-09 | [x] | Batch/expiry visibility, holds and waste | `inventory/batches.html`, stock batch ledger tests | FEFO, recalls and expired-stock policy fully verified in SM-18 | 08 |
| SM-10 | [x] | Purchase orders, partial goods receipt and supplier balances | purchase order/receiving screens and supplier balances | End-to-end request→quotation→GRN→credit note in SM-16 | 09 |
| SM-11 | [-] | Fast checkout for continuous scanner-based transactions | POS order create/detail, scan-add, payments | Dedicated single-screen cash till: scan→qty→tender→receipt→next sale; keyboard/focus/multi-tender and barcode replay test | 02, 23 |
| SM-12 | [-] | Weighted barcode labels and electronic scale integration | UoM fields exist; no verified certified scale/label adapter | EAN-13 embedded-price/weight parsing with checksums; scale tare/price-per-kg and supported hardware | 15 |
| SM-13 | [-] | Retail tax and fiscal receipt accuracy | line tax fields, receipts, optional EFRIS outbox | VAT inclusive/exclusive policy, rounding, discounts, split tender and URA-certified fiscal output | 17, 32 |
| SM-14 | [-] | Import and maintain a large product catalog | staff item forms/import groundwork | CSV template, preview, row diagnostics, safe upsert, SKU/barcode duplicate enforcement, bulk pricing | 27 |
| SM-15 | [-] | Shelf-label printing and barcode label design | outlet-scoped Shelf labels screen generates bounded A4 PDF tags from current outlet prices/barcodes; automatic label queue covers new products, price changes, imports and receiving, with manual queue, audited print completion/dismissal and recent history | Physical printer/media alignment, richer thermal layouts, weighed-label printer integration, scanner read-back and supported-hardware acceptance | 15 |
| SM-16 | [-] | Full supplier replenishment journey | PO, partial receiving, supplier balances and invoices | Purchase requests, quotation comparison, discrepancies, allocations, credit notes, due dates and supplier lead-time analytics | 09 |
| SM-17 | [-] | Stocktaking and blind/cycle counts | stock-count sessions, movements and staff screens | Offline handheld count, zones/aisles, blind double count, variance approval, import scans, count lock | 07, 16, 21 |
| SM-18 | [-] | FEFO, expiry, recall and shrink management | batches/expiry, stock write-off, ledger | Automatic FEFO reservation/consumption under concurrency, recall trace, sale block, damaged/expired disposal approvals | 08 |
| SM-19 | [-] | Low stock, dead stock, margin and reorder intelligence | `inventory/intelligence.html` with movement-based hints | Lead times, landed cost, sales velocity accuracy, days of cover, seasonality, explainable reorder suggestions | 07, 18 |
| SM-20 | [-] | Manager authorizations and fraud controls | transaction-bound manager PIN approval with different approver, outlet scope, expiry/replay evidence; retail refunds, line discounts, full-basket voids, cash payouts and manual stock write-offs are wired | Complete remaining applicable sensitive actions, API/service parity and deployed multi-manager till acceptance | 20, 21 |
| SM-21 | [-] | Offline cashier lane | offline queue/replay safety and UI | Explicit offline tender/amount limits, local privacy, device identity, conflict review and reconnection simulator | 16 |
| SM-22 | [-] | Customer history and loyalty | customer directory, points ledger, POS-linked customer records | Reward redemption, tiers, coupons, points liability, consent, customer-facing receipt balance | 05, 06 |
| SM-23 | [ ] | Retail credit accounts and credit limits | guest folios are not a general retail customer-credit engine | Authorized debt sales, aged debt, statements, payments, locks, bad-debt/writeoff approvals | 05, 32 |
| SM-24 | [-] | Layaway, deposits and collection pickup | no verified dedicated customer reservation workflow for goods | Reserve stock, partial deposits, expiry, collection and cancellation/refunds | 05, 09 |
| SM-25 | [-] | Wholesale pricing and customer price tiers | existing price/discount basis only | Pack/case pricing, tiered quantities, B2B price list, effective dates and quote conversion | 09, 18 |
| SM-26 | [-] | Pack/carton/unit conversion with purchase and sell units | Existing carton conversion plus tenant-scoped package definitions; package barcode/code resolves at cashier, package scans convert to base units, PO lines snapshot selected packages, and receiving converts package counts into the authoritative base-stock ledger | Finish supplier-specific packs/cost apportionment, package-aware imports, concurrency/browser acceptance and complete nonnegative-stock verification | 07, 08 |
| SM-27 | [ ] | Multi-branch transfers with dispatch/receipt discrepancy tracking | basic inventory transfers exist | In-transit ledger, sending/receiving accountability, short shipment and reconciliation | 07, 09 |
| SM-28 | [-] | Customer-facing display and queue management | configurable device shell, no complete verified live display | Display items/total/change, receipt number, queue/till call, secure output | 15, 23 |
| SM-29 | [-] | Till-side reports and management dashboards | sales summary and executive report foundation | Per-cashier/till/item/category profit, shift vs tender settlement, hourly peak, variance drill-down | 18, 19 |
| SM-30 | [ ] | Promotion engine for buy-X-get-Y, bundles and markdown scheduling | basic promotions/line discounts exist | Effective dates, multiple price rules, precedence, eligibility, margin floors, UI and regression suite | 06, 21 |
| SM-31 | [ ] | Supplier price lists and cost-change history | PO unit cost basis | Cost history, currency, landed/freight cost, margin alerts, suggested retail price, approvals | 09, 18 |
| SM-32 | [-] | Branch aisle/bin/shelf locator | outlet/stock fields, no evidenced detailed bin/location ledger | Shelf/bin IDs, picking path, mobile lookup and bin-count integration | 07, 25 |
| SM-33 | [-] | Search, staff lock/PIN and cashier ergonomics | role workspaces, global search, PIN locking, screen density settings | Real supermarket transaction stopwatch and keyboard/scanner/mobile accessibility audit | 02, 23–25 |
| SM-34 | [-] | Retail-specific setup, training and release | onboarding, local training command, release preflight | Demo sale, safe reset, real barcode printer/scanner/scale trials, offline/restore/rollback evidence | 27–33 |
| SM-35 | [-] | Loss-prevention reports | manager exception centre, repeated-void/manual-price exception sources, refund/discount/void/withdrawal/write-off approval evidence and scoped manager history exist | Add no-sale drawer-open evidence, shrink heat map/trend analytics, remaining price-override sources and deployed investigation acceptance | 03, 18, 22 |
| SM-36 | [ ] | Stock receiving invoice matching and electronic supplier documents | PO invoice/receipt basis | Three-way match PO–GRN–invoice, discrepancy approvals, duplicate supplier invoice protection and credit notes | 09, 32 |

**Current inventory (code-evidence only):** 10 existing foundations `[x]`, 20 partial `[-]`, 6 not evidenced `[ ]` (36 items). This does **not** mean these workflows passed physical/browser certification. Refresh counts whenever a checkbox changes.

## Supermarket priority and implementation order

### Priority 0 — reliable tills, stock, cash and loss prevention (do these first)

- [ ] **SM-P0.1 Fast cashier lane (SM-11, SM-33):** one responsive scan-first checkout with visible product/quantity/price, running total, hold/resume, exact tender/change, print and next-customer flow. Keep existing order/payment service. Test 100 successive items, unknown barcode, double-scan, weighted line, rapid keyboard input, session lock and two cashiers.
- [ ] **SM-P0.2 Catalog integrity (SM-14):** import large SKUs from CSV with row-by-row preview, duplicate barcode detection, immutable identity handling, bulk price/unit/cost edits and rollback on bad file. Test 1k–10k row files, safe re-import and tenant isolation.
- [ ] **SM-P0.3 Receipt and refund correctness (SM-06, SM-13):** taxable/zero-rated lines, discount order, split tender, exact change, partial returns/refunds, original receipt, manager approval and audit. No silent tax or stock adjustments.
- [ ] **SM-P0.4 Stock trust (SM-08, SM-17, SM-18, SM-26):** multi-unit purchases, stock-count adjustments, transfers, batch holds, expiry and concurrent till deduction; prove inventory never goes negative unexpectedly.
- [ ] **SM-P0.5 Workstation and cashier control (SM-07, SM-20, SM-35):** PIN handoff/auto-lock, own till and float, drops/payouts, counted close, exceptions, approval audit and manager dashboard.
- [ ] **SM-P0.6 Tenant separation and permissions (SM-01, SM-34):** an independent retail workspace must not show lodging, restaurant or bar language; tenant, branch and cashier permission limits must hold in staff pages and API.

### Priority 1 — make supermarket operations efficient every day

- [ ] **SM-P1.1 Replenishment and receiving (SM-16, SM-19, SM-36):** suggested orders based on usage and lead time, PO approvals, scanning goods receipt, supplier invoice matching, shortages and credit notes.
- [ ] **SM-P1.2 Item labels and weighing (SM-12, SM-15):** embedded-weight barcodes, price labels, shelf tags and physical hardware validation; do not claim generic browser printing is a certified scale adapter.
- [ ] **SM-P1.3 Shrink, expiry and recalls (SM-18, SM-35):** dated batch trace, sale block for recalls, controlled spoilage write-off and manager exception drill-down.
- [ ] **SM-P1.4 Better costing and reporting (SM-19, SM-29, SM-31):** margin by item and category from verifiable cost basis; no invented profit when costs are absent.
- [ ] **SM-P1.5 Multi-branch stock operations (SM-27, SM-32):** dispatch, transit, receipt/discrepancy, aisle/bin finder and separate branch stock reports.

### Priority 2 — competitive retail features

- [ ] **SM-P2.1 Promotions and customer rewards (SM-22, SM-30):** discounts, coupons, bundles, expiry, simple points redemption and anti-abuse policy.
- [ ] **SM-P2.2 Wholesale and credit (SM-23–SM-25):** pack/carton, wholesale prices, customer credit/limits/statements and layaway with finance-safe posting rules.
- [ ] **SM-P2.3 Customer display and training (SM-28, SM-34):** secure customer-facing till display, guided supermarket training and safe demonstration dataset.

## Definition of Done — every supermarket item

1. **Backend:** one authoritative business service; money, tax and stock are decimal-safe and idempotent; no duplicated logic.
2. **UI:** accessible from named staff navigation; completes end-to-end on desktop, laptop, tablet and narrow phone (not merely an unused form or model); empty, error, success, retry and permission-denied states.
3. **Permissions:** proper manager/cashier/storekeeper roles, outlet and tenant scope; shared-terminal PIN/lock; deny unauthorized API mutations.
4. **Accounting:** exact receipts, refunds, stock movement, payments, tax and supplier balances; linked audit record; no historical rewriting.
5. **Verification:** focused tests, full green exact-head CI, production-style PostgreSQL transaction/row-security tests, responsive browser exercises, and real hardware/provider certification where applicable.
6. **Evidence log:** commit SHA, test command/result, screens tested, migrations, any unsupported environment/provider/hardware, and remaining exception. **Only then** update `[x]` status.

## Release and progress log

| Date | Head/release | Scope | Automated checks | Browser/PostgreSQL/hardware | Decision |
|---|---|---|---|---|---|
| 2026-10-16 | Roadmap baseline | Supermarket evidence assessment and prioritized backlog | Earlier suite runs existed; exact-head verification must be checked before certifying | Not established by this document | Tracking established; no new feature falsely certified |

When implementing, update the affected SM-ID row, the P0/P1/P2 acceptance item, and the matching numbered phase in `SUITE_IMPLEMENTATION_TODO.md`. Report **implemented, tested, and production-certified** separately. Avoid claiming percentages based only on a commit.

## 2026-10-16 — SM-P0.1 scan-first cashier implementation checkpoint

- Extended the **existing** supermarket order detail rather than adding a second POS. Open retail/supermarket orders now show a focused scanner form, quantity input, one-submit guard, scan status, and `/` hotkey to focus the barcode field. The backend still uses `StaffOrderScanAddForm` and `add_supermarket_line_by_code` for server-side validation, price and stock policy.
- On completed paid supermarket orders, the cashier can press **Next customer · new sale**. It submits an explicit CSRF-protected POST to the existing quick-create endpoint; visiting its URL by GET never creates an order. Existing receipt links remain on the order.
- Added staff integration tests checking scan page visibility, barcode-based line insertion and GET-vs-POST new sale behavior. These require the exact-commit CI run before verification.
- **SM-11 / SM-P0.1 remain `[-]` / `[ ]` respectively**. A production cashier lane still needs settled tender/change display, fast scanner loop under real hardware, hold/resume, large baskets, focused flow order, and device/browser regression. This checkpoint is meaningful end-user UI implementation, **not completion**.
- Next supermarket work targets catalog reliability and cashier throughput without changing any bar/hotel staff screen.

## 2026-10-16 — SM-P0.1 cash tender and change checkpoint

- Inspected the existing staff payment service: it records the **amount applied to the sale**, not total notes handed to the cashier. Preserved the payment ledger and full/partial tender accounting rules rather than posting overpayments or inventing change transactions.
- Added a supermarket-only, accessible cash tender calculator alongside the existing payment form. The cashier can enter cash physically received, see change due, and automatically populate the actual outstanding amount when Cash is selected. Short cash prompts the operator to use normal partial payment; card/mobile money tender rules are unchanged.
- Added an integration assertion for checkout page rendering and the calculator, conditional on the existing server permission to collect payments. This is **not** a certified overpayment/change workflow: physically tendered cash is not persisted and the helper is browser-side only.
- Research basis: current Odoo POS checkout documentation distinguishes cash tender requiring change from exact payment, while receipt specifications require reliable paid-method disclosure. Sources: https://www.odoo.com/documentation/20.0/applications/sales/point_of_sale/payment_methods.html and https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/use/receipts.html .
- **SM-P0.1 remains open** until scanner performance, exact settlement, server-side tender audit, real receipt printing, hold/resume, narrow-screen/browser testing and full-CI sign-off are demonstrated.

## 2026-10-16 — SM-P0.1 checkout hardening checkpoint

- Reviewed current official Odoo POS workflow (https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/use.html) and Shopify partial/split payment instructions (https://help.shopify.com/en/manual/sell-in-person/shopify-pos/payment-management/multiple-partial-payments). Existing order/payment services already support separate partial tender records, remaining-balance validation, held orders and explicit POST-only next sale, so those are retained.
- Corrected scan-first UI regression: the pre-existing staff supermarket test expects the visible **Scan or enter PLU** wording. Previous exact-head run `38933163900` reported **540 passed, 1 failed, 5 skipped** owing to this missing UI label; the label is now restored.
- The cashier payment form now carries a stable UUID on the rendered form and passes it to the existing idempotent settlement service. Reusing the same form/request identity no longer generates a new key on each submission. Missing keys from older forms still follow the previous code path. Tests cover form identity persistence.
- The existing hold and resume cards on **Orders** and tender/method choices on **Order details** remain authoritative; no duplicate register/payment service introduced. Cash change remains an on-screen calculator, not a money movement.
- **Completion criteria not silently waived:** exact-head CI success, browser/device scan-to-tender performance, actual receipt printing, two-till concurrency, backend transaction consistency and tender audit remain separate acceptance gates. Do not claim hardware certification merely because the UI renders.

## 2026-10-16 — retail identity is anonymous and table-free

- The **default retail/supermarket transaction is an anonymous walk-in sale**: no customer profile, phone, name, guest folio, room or table is required to open, scan, pay or print a receipt. The transaction is identified by order/receipt and register, not a hospitality table number.
- In the shared order detail, supermarket/retail outlets now hide the hotel/bar tab label and customer-record controls unless the order already has an explicitly linked customer. Hospitality outlets retain their existing table/customer behavior. The orders list labels held retail transactions as **baskets**, not tables/tabs.
- Added integration assertions for anonymous checkout and supermarket basket terminology. Explicit customer linking is optional for identified loyalty/credit cases and must respect permissions; it is never a prerequisite for normal sale.
- This is a software/UI separation, not proof of physical hardware certification. Exact-head CI verification remains necessary before closing SM-P0.1.

## 2026-10-16 — SM-P0.2 larger safeguarded catalog import

- Reused existing `apps.console.catalog_import` (preview, UTF-8 checking, per-row diagnostics, tenant SKU/barcode duplicate detection, atomic all-or-nothing creation and no stock posting).
- Increased bounded batch size from **250 to 1,000 items**, maximum upload **1 MB**. The owner-facing form displays the new limits. Large shops can submit successive batches without overwhelming one web transaction; this does not support 10,000 rows in a single request.
- Updated existing batch-limit regression and added a **300-item import** test, confirming unique created SKUs and counts. No existing SKU overwrite or silent price change has been enabled.
- Research: Shopify advises validating CSV format before import, using a test subset, and treating overwrites cautiously because blank fields may replace existing data. https://help.shopify.com/en/manual/products/import-export/import-products
- **SM-14 / SM-P0.2 remain open** until end-user stock catalog assignment, safe update/upsert policy, larger-file performance, duplicate concurrency, full exact-head CI and browser review are checked. Physical store inventory must be received via stock ledger, not CSV product creation.

## 2026-10-16 — SM-P0.2 catalog integrity and tenant backup

- Verified the existing catalog importer against current official Shopify CSV import guidance and Odoo barcode documentation. Preserved a create-only import model rather than silently overwriting product identity, historical prices, or stock.
- Added validation for truncated required CSV fields and embedded multiline/control-character fields; malformed rows fail the entire import without creating earlier rows. Added regression tests.
- Added **Export my current products** to the tenant owner/administrator catalog-import screen. It exports only that business's catalog metadata (category, name, price, SKU, barcode, tracking, reorder level, UoM, tax and description); it never exports customer data or inventory quantities and uses a private, no-store response. Regression coverage confirms tenant scoping.
- Standardized CSV size-limit messages to **1 MB** and maintained the 1,000-row per-batch limit. Export is for owner review/backup before changes; imported records still cannot overwrite existing SKUs, and exports exceeding 1,000 rows require splitting before reimport.
- **Outstanding SM-P0.2:** approved upsert/price-change workflow, change audit/history and rollback policy, catalog-to-outlet availability management, PostgreSQL large-batch performance and full end-user verification. Do not mark complete until exact-commit CI passes.

## 2026-10-16 — SM-P0.2 bulk price editor end-user flow

- Added a complete owner-facing **bulk base price worksheet** to the existing catalog import screen, including scoped current-price download, explicit `sku,old_price,new_price` format, preview and apply actions. The UI uses a dedicated review step; applying re-uploads and rechecks the file.
- Existing product definitions are **not** silently overwritten by creation CSVs. Base prices change only in the explicit pricing flow. The service locks matching product rows, enforces unique SKU and expected previous price, updates the entire batch atomically or not at all, and writes a per-item before/after audit trail.
- Restricted this path to the existing tenant-owner/admin console. No stock, tax, inventory receipt, historical order, customer or branch-level price overrides are rewritten.
- Added regression tests for stale prices, duplicates, cross-tenant attempts, stock invariance and audit evidence. CI must pass on the exact commit before changing SM-P0.2 to completed.
- Research: Shopify's official CSV overwrite guidance cautions that included empty fields may erase existing values, so this feature uses explicit old/new fields and preserves a create-only ordinary import. https://help.shopify.com/en/manual/products/import-export/import-products/

## 2026-10-16 — CSV control-character regression repair

- Exact-head run `38936601021` found **550 passed, 1 failed, 5 skipped**. The failed malformed-CSV test revealed that the importer checked written backslash sequences instead of actual embedded NUL/newline/carriage-return characters. Corrected the parser's detection in commit `038a55793fa2128b45816e6eb2686d49f8dfc6e9`.
- This check prevents fields with embedded line breaks from being accepted as ordinary product names or codes; existing atomic import and duplicate identity controls remain unchanged.
- Reference: [Shopify's current CSV import guidance](https://help.shopify.com/en/manual/products/import-export/import-products/) emphasizes format checks, safe handling of existing records and validating files before applying changes.
- Do not mark SM-P0.2 complete until the corrected exact-head CI passes and browser/PostgreSQL import and price-change journeys are verified.

## 2026-10-16 — SM-P0.4 minimum stock signal

- Preserved the existing inventory and stock-planning services. Extended `stock_coverage_snapshot` with `out_of_stock` and `reorder_shortfall` based strictly on recorded on-hand quantity and the SKU's configured minimum. A zero-stock/no-sales-history item remains **unknown demand**, not a fabricated replenishment forecast.
- Added focused tests for stocked-but-below-minimum items and a zero-stock grocery item; branch/tenant filtering remains intact.
- Research: [Odoo reordering rules](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/reordering_rules.html) distinguish configured reorder levels, current/forecasted stock and vendor lead time. This checkpoint intentionally calculates minimum-level shortfall only; supplier lead-time replenishment remains in the existing staff planning screen.
- This is one stock-intelligence service improvement, **not a completed SM-P0.4 or Phase 07**. The remaining stock acceptance covers count discrepancy, FEFO, receipts, multi-unit conversion, mobile stocktake and concurrent till stock deduction. Exact-head CI and browser/PostgreSQL proof are still required.

## 2026-10-16 — SM-P0.4 stocktake posting safety

- Reused the existing `complete_stock_count_session` service. All submitted lines now undergo **preflight checks before the first stock balance, batch allocation, movement or count line is written**. Duplicate item lines, negative counts, non-finite decimal numbers, excessive precision and out-of-range quantities produce explicit validation errors.
- Added `test_stock_count_preflight.py` coverage for duplicates and malformed counts, asserting the original balance and stock movement ledger remain unchanged when invalid counts are rejected. Existing outlet authorization and tenant scoping remain enforced.
- This protects existing supermarket/grocery stocktake workflows and does not bypass batch-aware stock posting. It is not full stocktaking certification: physical count variance approval, mobile scanning, concurrent close/count and PostgreSQL locking must still be exercised.
- Current work was committed to `origin/main` and must pass full exact-head CI. Do not close SM-P0.4 solely from source edits.

## 2026-10-16 — Batched supermarket stocktake and goods-receiving integrity

- Prior supermarket stock-count head `468c5aebb29a` **passed GitHub Actions** (run `38938674809`). The current batch builds on that green foundation.
- Existing stock-count completion now validates duplicate item IDs and malformed, negative, non-finite and over-precision quantities **before posting any item**. New `test_stock_count_preflight.py` exercises rejection without stock/ledger changes.
- Purchase-order receiving now validates *all delivery-line quantities* up front, rejecting malformed, negative, non-finite, over-precision and duplicate positive line IDs before a receipt is created; delivery references are normalized, capped at 128 characters and compared without case sensitivity to reduce accidentally repeated supplier deliveries. New service tests assert rejected deliveries leave no receipt, stock balance or movement.
- Reused the existing authenticated, outlet-scoped `receive_purchase_order_goods` / `complete_stock_count_session` domain services. Both continue using atomic transactions and existing batch allocations; no parallel receiving system introduced.
- **Hardware and certification boundary:** exact-head CI for this batch, PostgreSQL concurrent receiving/counting, physical scanner and full mobile receiving workflows remain separate gates. SM-P0.4, SM-17, SM-36 and Phase 09 are **not fully closed** by this work alone.

## 2026-10-16 — Receiving batch: audit, delivery accuracy and cashier-friendly UI

- Improved the existing purchase-order goods-receiving flow rather than creating a parallel inventory subsystem. Every completed receipt now logs a **purchase.goods_received** audit event with purchase order, delivery reference, discrepancies and accepted quantities per line, in addition to the existing stock-movement ledger.
- Added end-to-end service regression for **partial receiving** (8 of 20 units), verifying actual posted balance and traceable receipt data, and that a repeated supplier reference with different capitalization cannot receive the same delivery again.
- On the receiving page, added explicit guidance to record only verified/accepted quantities, keep missing/damaged units out of saleable stock, and document discrepancies. Prevents accidental repeat button clicks on the same browser form while preserving backend duplicate-reference enforcement.
- Research baseline: [Shopify's receiving guidelines](https://help.shopify.com/en/manual/products/inventory/purchase-orders/receiving-inventory) distinguish accepted vs missing/damaged goods, partial shipments, and reconciliation. This implementation continues to represent goods accepted as stock, with damaged/missing items noted for follow-up; a fully structured rejected-goods/backorder subsystem is **not yet claimed**.
- The earlier stock count / delivery validation batch was not independently green at the latest check: CI workflows were superseded/cancelled by later commits. Current batch must pass the exact-head CI before marking receiving complete. Physical GRN, multi-worker and supplier-credit-note certification remain open.


## 2026-10-17 — F4 supplier payment attribution and role-safe purchasing API

- Existing supplier PO/invoice/credit/payment and goods-receiving flows are now supplemented with invoice-level payment attribution, aged invoice balances and an explicit manager reconciliation action for previously unassigned payments. The supplier's original cash expense and stock ledger remain unchanged when linking payment references. Exact-amount and over-credit guards protect the selected invoice; historic payments are never automatically allocated.
- Purchase/supplier API mutations now use the **existing purchasing capability policy**: assigned storekeepers may receive accepted goods; only purchasing managers may create/edit suppliers/POs, confirm unit costs, record invoices, pay suppliers or reconcile old financial payments. Accountants remain read-only.
- F4/SM-10/16/19/31/36 remain **partially implemented** until source-line three-way quantity/price matching, physically verified vendor returns, real PostgreSQL concurrent settlement and mobile/browser acceptance are evidenced. CI is required for the exact final SHA.


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


### Owner administration visual parity — 21 October 2026

- [x] Store-owner administration shell on `/console/` remains separate from platform and bar/hotel consoles; retail/supermarket-only multi-line tenants also get the store shell.
- [x] Guided setup has numbered required tasks, true backend progress state, optional tasks, expandable problem controls and go-live checks; no automatic claim that payment or printer hardware is certified.
- [x] Business settings, branches, sales areas, product list, categories and corresponding create/edit forms share a consistent retail visual system, with clear empty states and mobile table scrolling.
- [x] Product advanced settings are collapsed by default without removing underlying fields or saving an incomplete form; validation errors expand the group.
- [x] Per-sales-area pricing list, edit and removal confirmation use plain retail terms without affecting store inventory or financial calculations.
- [x] CSV product import is aligned with the store-owner navigation without changing its preview/apply validation rules.
- [x] Added `backend/tests/test_grocery_owner_console_pages.py` covering owner routing, cross-profile presentation, forms and links.
- [ ] GitHub Actions SQLite + PostgreSQL checks for the **combined latest commit** (do not treat newly committed tests as a passing run).
- [ ] Real browser check at a deployed owner site: desktop/tablet/phone setup, stock/pricing flows, responsive navigation, keyboard, error handling and print-device integration.
- [ ] Confirm live tenant's deployment pulled current `origin/main`, then collect final screenshots against the approved store owner reference.

**Scope:** These are navigation/presentation changes and regression tests. They do not certify F6 operational acceptance or claim all remaining business-specific modules are complete.


## 2026-10-24 — Cashier queue: held and part-paid baskets (owner acceptance contract)

**Current-code inspection:** `backend/apps/staff/views_ops.py::_post_hold_order` already clears the retail customer-display active association and redirects a successfully held supermarket/retail order to `staff-retail-pos-entry`, so it should no longer occupy the active cashier screen. It currently **rejects `order.is_paid`**, and the underlying service/financial state transitions must be reviewed before expanding this to partially paid orders. This is a requirements/verification checkpoint **not** a claim that partially paid holding is delivered.

- [ ] For an unpaid active basket, **Hold** saves its exact lines, quantities, discounts, prices, operator/outlet, and optional short retrieval label; immediately removes it from the active workstation display and opens an empty new-sale screen. The customer display must stop showing the departed customer's sensitive/active basket.
- [ ] **Held sales** is a separate searchable queue (reference, cashier, creation time, amount, and payment state), not an overlay permanently consuming the current checkout canvas. A cashier can retrieve a held basket only within authorized tenant/outlet/workstation rules; record retrieval and subsequent modifications in audit history.
- [ ] A **partially paid** basket can be held *only after* verifying the existing `Order.is_paid`, tender, closing, remaining-due, refund and shift-ledger semantics. Already captured tenders remain immutable and allocated to the original basket; the basket displays paid and due separately. Do not recognize the same cash twice, silently refund, or allow a completed fully paid sale to be reopened.
- [ ] On retrieval, **Pay remaining / Complete sale** supports additional valid tenders, posts each payment once (idempotent retry identity), and closes/releases only after a verified full settlement. A cashier may switch to the next customer while the part-paid basket is held.
- [ ] Lock per-order changes and concurrent retrieval/settlement; use a verified transaction with re-read of order/tenders. Reject double payment, overpayment, cross-tenant/cross-outlet retrieval and attempts to use another worker's basket without permission.
- [ ] Check anonymous supermarket customers by default; guest/table/room identification is never mandatory for this flow. Honor selected tenant currency (e.g., UGX), without fallback to USD if a tenant explicitly chose UGX.
- [ ] Regression test hold → new basket → retrieve → amend → settle, part-pay → hold → another sale → retrieve → final tender, browser back/refresh, simultaneous tills, failed provider callbacks, shift closure, and receipt/return/audit snapshots; perform PostgreSQL and real browser/device acceptance separately.

**Release status:** Unpaid hold redirect is present in source. The partially paid lifecycle, ledger invariants, cross-till behavior and end-to-end UI are **open**, and neither F5/F6 nor release certification can be closed from this document alone.


### 2026-10-24 closeout implementation checkpoint

- [x] **Source-level safeguard committed:** `cancel_open_unpaid_order` now refuses to cancel a basket with any recorded `Payment`; partial tenders cannot be discarded by changing only the order status. Commit `14816d806f9dcba9a4905238e08bfca6b1217658`.
- [x] **Regression test added:** `test_part_paid_basket_can_be_held_but_not_voided` checks the existing hold service accepts a partially paid open order, cancellation raises validation error, and the payment remains. Commit `f8a61c8298e524f5a61a091dbcc43c3408bb7a18`.
- [ ] **Focused automated test passing at exact head:** not executed in this connector session.
- [ ] **Remaining-due and retrieval in an actual cashier browser:** still requires verified end-to-end interaction and screenshots against the approved UI.
- [ ] **Full suite, PostgreSQL concurrent checkout, provider callbacks, real Uganda till hardware, production rollout:** no certification evidence collected in this session.

Do not conflate a committed regression test with a passing test or a completed roadmap phase.


### 2026-10-26 — SM-15 shelf labels + cashier no-refresh discount checkpoint

- Added **Inventory → Shelf labels** for retail/supermarket workspaces. It reuses the tenant/outlet-scoped product catalog and outlet price overrides; selected products generate a bounded A4 PDF. Stored product barcodes are rendered as Code 128, while products without a barcode remain clearly non-scannable rather than receiving an invented identifier. Requests are limited to 20 copies per product and 120 labels per PDF.
- Shelf-label output remains software-only acceptance. The label-change queue is now implemented for new products, price changes, imports and receiving, including manual requests, pending-reason filtering, printed completion, audited dismissal and recent history. Physical printer model/media alignment, thermal/shelf-tag dimensions and barcode scanner read-back remain open, so **SM-15 stays [-]**, not complete.
- Manager-approved retail line discounts now support the existing asynchronous checkout pattern: the server still requires the exact scoped manager PIN approval and idempotent request identity, returns JSON to supported browsers, rotates the one-time request key after success and refreshes basket/totals without a whole-page reload. Native form POST remains the fallback.
- These commits require exact-head CI and deployed browser acceptance. They do not certify physical label printers, barcode scanners, supervisor-PIN usability on real tills or every remaining cashier mutation.


### 2026-10-26 — SM-20 / SM-35 approval and loss-prevention checkpoint

- The central sensitive-action approval service now enforces a different PIN-enabled manager, exact intent identity, outlet scope and replay-safe evidence. Retail refunds, line discounts, full-basket voids, register payouts and manual stock write-offs use it.
- Manual stock decreases cannot bypass approval through CSV; adjust-out/waste rows are rejected from bulk upload and must use the manager-approved movement form.
- The existing manager workspace exposes scoped approval evidence alongside exception follow-up. SM-35 therefore moves from not evidenced to partial, but remains open for no-sale drawer events, richer shrink/price-override analytics and deployed investigation drills.
- SM-20 remains partial until every applicable sensitive mutation and API/service route shares the same boundary and real multi-manager register acceptance is recorded.


### 2026-10-26 — F5 cashier-attributed void evidence

- The existing manager exception center now attributes voided lines to the staff user who performed the void and shows that worker's void count across the configured review window, alongside repeated voids on the same sale. This preserves fast pre-payment basket correction while making repeated cashier void patterns visible for investigation.
- No new loss-prevention dashboard or duplicate event store was introduced; the existing `OrderLine.voided_by`, exception review workflow and manager source links are reused.
- SM-35 advances from not evidenced to partial software implementation. No-sale drawer events, stronger shift/cashier trend aggregation, price-override approval evidence and physical/production acceptance remain open. Exact-head CI is required before treating this checkpoint as verified.


## 2026-10-27 — R1 merchandise foundation started

- Added the organized retail expansion plan in `docs/RETAIL_EXPANSION_ROADMAP_2026-10-27.md`; it groups missing QuickBooks-depth retail features into eight related workstreams rather than scattering them across unrelated screens.
- Started R1 without replacing the existing catalog or stock ledger. `MenuItem` remains the concrete sellable SKU; optional `ProductFamily` records group related variants while simple products remain unchanged.
- Added tenant-scoped `ProductPackage` definitions with base-unit conversion, package barcode/code, optional package selling price and sell/purchase flags. Console UI now exposes Product families and per-product Packages & barcodes.
- Added PostgreSQL RLS for the new tenant-owned merchandise tables and blocked ambiguous base-product/package barcode and SKU collisions in the owner catalog forms.
- Package definitions are **not yet consumed by checkout or purchasing** in this checkpoint. Scanner/package price conversion, variant option matrix, package-aware receiving and complete migration/CI/browser acceptance remain R1 work; no completed status is claimed.
