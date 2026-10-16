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
| SM-12 | [ ] | Weighted barcode labels and electronic scale integration | UoM fields exist; no verified certified scale/label adapter | EAN-13 embedded-price/weight parsing with checksums; scale tare/price-per-kg and supported hardware | 15 |
| SM-13 | [-] | Retail tax and fiscal receipt accuracy | line tax fields, receipts, optional EFRIS outbox | VAT inclusive/exclusive policy, rounding, discounts, split tender and URA-certified fiscal output | 17, 32 |
| SM-14 | [-] | Import and maintain a large product catalog | staff item forms/import groundwork | CSV template, preview, row diagnostics, safe upsert, SKU/barcode duplicate enforcement, bulk pricing | 27 |
| SM-15 | [ ] | Shelf-label printing and barcode label design | printable receipts exist, not shelf label workflow | Price-label templates, product/barcode/weight printing, change queue, supported printers | 15 |
| SM-16 | [-] | Full supplier replenishment journey | PO, partial receiving, supplier balances and invoices | Purchase requests, quotation comparison, discrepancies, allocations, credit notes, due dates and supplier lead-time analytics | 09 |
| SM-17 | [-] | Stocktaking and blind/cycle counts | stock-count sessions, movements and staff screens | Offline handheld count, zones/aisles, blind double count, variance approval, import scans, count lock | 07, 16, 21 |
| SM-18 | [-] | FEFO, expiry, recall and shrink management | batches/expiry, stock write-off, ledger | Automatic FEFO reservation/consumption under concurrency, recall trace, sale block, damaged/expired disposal approvals | 08 |
| SM-19 | [-] | Low stock, dead stock, margin and reorder intelligence | `inventory/intelligence.html` with movement-based hints | Lead times, landed cost, sales velocity accuracy, days of cover, seasonality, explainable reorder suggestions | 07, 18 |
| SM-20 | [-] | Manager authorizations and fraud controls | manager roles, exception center, partial action eligibility | Separate manager PIN, exact sale/discount/price/return approval, expiry/replay protection and auditable overrides | 20, 21 |
| SM-21 | [-] | Offline cashier lane | offline queue/replay safety and UI | Explicit offline tender/amount limits, local privacy, device identity, conflict review and reconnection simulator | 16 |
| SM-22 | [-] | Customer history and loyalty | customer directory, points ledger, POS-linked customer records | Reward redemption, tiers, coupons, points liability, consent, customer-facing receipt balance | 05, 06 |
| SM-23 | [ ] | Retail credit accounts and credit limits | guest folios are not a general retail customer-credit engine | Authorized debt sales, aged debt, statements, payments, locks, bad-debt/writeoff approvals | 05, 32 |
| SM-24 | [ ] | Layaway, deposits and collection pickup | no verified dedicated customer reservation workflow for goods | Reserve stock, partial deposits, expiry, collection and cancellation/refunds | 05, 09 |
| SM-25 | [ ] | Wholesale pricing and customer price tiers | existing price/discount basis only | Pack/case pricing, tiered quantities, B2B price list, effective dates and quote conversion | 09, 18 |
| SM-26 | [ ] | Pack/carton/unit conversion with purchase and sell units | UoM exists; no verified multi-pack ledger | 1 carton→N pieces, cost apportionment, barcode for each size and nonnegative stock rules | 07, 08 |
| SM-27 | [ ] | Multi-branch transfers with dispatch/receipt discrepancy tracking | basic inventory transfers exist | In-transit ledger, sending/receiving accountability, short shipment and reconciliation | 07, 09 |
| SM-28 | [ ] | Customer-facing display and queue management | configurable device shell, no complete verified live display | Display items/total/change, receipt number, queue/till call, secure output | 15, 23 |
| SM-29 | [-] | Till-side reports and management dashboards | sales summary and executive report foundation | Per-cashier/till/item/category profit, shift vs tender settlement, hourly peak, variance drill-down | 18, 19 |
| SM-30 | [ ] | Promotion engine for buy-X-get-Y, bundles and markdown scheduling | basic promotions/line discounts exist | Effective dates, multiple price rules, precedence, eligibility, margin floors, UI and regression suite | 06, 21 |
| SM-31 | [ ] | Supplier price lists and cost-change history | PO unit cost basis | Cost history, currency, landed/freight cost, margin alerts, suggested retail price, approvals | 09, 18 |
| SM-32 | [ ] | Branch aisle/bin/shelf locator | outlet/stock fields, no evidenced detailed bin/location ledger | Shelf/bin IDs, picking path, mobile lookup and bin-count integration | 07, 25 |
| SM-33 | [-] | Search, staff lock/PIN and cashier ergonomics | role workspaces, global search, PIN locking, screen density settings | Real supermarket transaction stopwatch and keyboard/scanner/mobile accessibility audit | 02, 23–25 |
| SM-34 | [-] | Retail-specific setup, training and release | onboarding, local training command, release preflight | Demo sale, safe reset, real barcode printer/scanner/scale trials, offline/restore/rollback evidence | 27–33 |
| SM-35 | [ ] | Loss-prevention reports | manager exceptions and refund events exist | Suspicious refunds, repeated voids, no-sale drawer opens, price overrides, shrink heat map and actionable audit | 03, 18, 22 |
| SM-36 | [ ] | Stock receiving invoice matching and electronic supplier documents | PO invoice/receipt basis | Three-way match PO–GRN–invoice, discrepancy approvals, duplicate supplier invoice protection and credit notes | 09, 32 |

**Current inventory (code-evidence only):** 10 existing foundations `[x]`, 13 partial `[-]`, 13 not evidenced `[ ]` (36 items). This does **not** mean 10 workflows passed physical/browser certification. Refresh counts whenever a checkbox changes.

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
