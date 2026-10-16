# Supermarket fast track → resume the full 34-phase suite

**16 October 2026 | Execution contract, not a completion claim**

Source of truth for capability details: [36-item supermarket checklist](SUPERMARKET_IMPLEMENTATION_CHECKLIST.md).
Parent plan: [34-phase suite implementation](SUITE_IMPLEMENTATION_TODO.md).

## Goal and guardrails

Bring independent supermarket and grocery operations to a demonstrably safe, usable daily-operating standard **before** returning to the interrupted full-suite roadmap. Reuse existing POS, inventory, procurement, finance and permission services. No customer names, tables, room numbers or hotel/bar language are required for an ordinary anonymous grocery sale. Optional loyalty remains optional.

Implement in larger coherent batches; no micro-phase ping-pong. Each batch includes backend, staff/owner UI, responsive navigation, permissions, audit trail, regression tests and documentation. **Never** equate code pushed to `main` with passing CI, browser acceptance or hardware certification.

## Accelerated sequence (six delivery batches)

| Batch | Scope / supermarket IDs | Definition of done |
| --- | --- | --- |
| **F1 — Checkout and retail separation** | SM-01, 03, 07, 11, 20, 33, 34 | Anonymous walk-in sale with scan/PLU, quantity, discounts within permission, held/resumed basket, partial/mixed tender, change, receipt and immediate next sale. Cashier lock/handoff and independent retail navigation. Unknown/repeated barcode and two-till tests. |
| **F2 — Catalog, pricing and fiscal correctness** | SM-02, 04, 06, 13, 14, 15 | Create/import/export and safe bulk price updates with preview, tenant scope and duplicate checks; accurate tax/discount/rounding/refund receipts; labels where supported. Explicit manual or certified EFRIS testing boundary. |
| **F3 — Reliable stock and expiry** | SM-08, 09, 17, 18, 26, 27 | Count/approval/variance trace, receipts, case-to-unit conversions where modeled, safe batch FEFO/holds and expiry, transfers with accountability, nonnegative stock under concurrent tills and returns. |
| **F4 — Purchasing and supplier financial matching** | SM-10, 16, 19, 31, 36 | Supplier → purchase order → partial or disputed goods receipt → invoice matching → supplier settlement/credit adjustment, auditable quantities and amounts; stock reorder insights without invented demand/cost. |
| **F5 — Manager oversight and operational reports** | SM-05, 20, 29, 30, 35 | Cashier shift/tender reconciliation, exception approval, suspicious refunds/voids, cost-grounded margin reports, tested promotion precedence and manager drill-downs. |
| **F6 — Finish optional/store-specific capabilities and release acceptance** | SM-12, 21–25, 28, 32, 34, 35 | Hardware-specific scale/weight barcodes/display, safe offline policies, opted-in loyalty, credit/layaway/wholesale, shelf locations, accessibility and desktop/mobile/tablet browser checks. Any external hardware/integration not testable in CI remains explicitly unverified, never silently marked complete. |

## Execution rules for speed without repeating mistakes

1. Finish **one batch end-to-end**, not only a model or backend service. Inspect what is already in the repository and improve it; no duplication.
2. Research current official product documentation and applicable Uganda fiscal requirements **when implementing each relevant capability**. Record sources and design decisions beside each batch.
3. Build a realistic integration test from ordinary anonymous sale through financial posting, inventory and receipt, and regression tests for duplicated requests, cross-tenant access, invalid counts, refunds and concurrency.
4. Use one cohesive commit set per batch where feasible, then obtain a **passing exact-main-commit CI run**. Do not keep restarting CI with documentation-only commits while the suite runs.
5. End each batch with a concise result: implemented, tested, CI status, not verifiable without physical hardware/production, and next batch. No questions or approval prompts.
6. A capability checkbox changes to complete only when its end-user path and relevant acceptance pass. Verified foundations in the original list are not automatically production-ready.
7. Avoid deploying, migrating or touching real financial/stock balances without production safeguards. Preserve data and rollback paths.

## Exit gate and handoff to the previous whole-system roadmap

After F1–F6, reconcile **every SM-01 through SM-36** item with evidence, with clear exceptions for hardware/provider certifications outside the available environment. Do not label the supermarket complete if key daily workflows remain partial. Capture Git commit, passing CI, browser/device scope and real-hardware tests separately. Then **resume** [the original 34-phase plan](SUITE_IMPLEMENTATION_TODO.md) at the first incomplete phase shown in [the progress board](IMPLEMENTATION_PROGRESS.md), without resetting finished work or creating a second roadmap.

**Baseline at planning time:** 10 code-evidenced foundations, 13 partial, 13 not evidenced. This is an inventory of capabilities, not percentage production readiness. Latest known checkout/receiving work is committed but exact-commit CI and physical acceptance require checking before crediting completion.

## F1 execution checkpoint — 16 October 2026

- **Implemented in code:** Refactored the supermarket cashier JavaScript so scan controls and cash-tender helper initialise independently; a missing/disabled scanner must not suppress payment guidance. Scanner quantity input rejects nonfinite, non-positive and greater-than-3-decimal entries. Tender input checks nonnegative cash with at most 2 decimals and computes change in integer cents, while only the amount due is populated in the existing payment form. Added cashier page regression assertions.
- **Already present, to retain:** Anonymous walk-in checkout, barcode/PLU scan service, hold/resume via Orders, existing idempotent payment service, payment method and partial payment choices, receipts, workstations and shifts.
- **Outstanding before F1 close:** repeat-scan and two-register concurrency integration, browser/end-user walkthrough, verified cashier handoff/auto-lock, receipt/printer and keyboard/device testing. Do not mark F1 complete from these UX changes alone.
- **Research principle:** money credited to a sale is not the total tendered by a customer; explicit cash-change computation must never mutate the ledger or overpay a closed sale. Actual calculation of payments remains server-side.

### F1 cashier payment submission protection — 16 October 2026

- Added an explicit marker to the existing payment form and supermarket-only browser guard preventing multiple submits while the request is pending. The existing stable payment UUID and server idempotency record remain authoritative; this browser safeguard is secondary. A regression test checks the page and request key.
- Implemented now: scanner quantity precision guard, cents-based cash change helper, independent scanner/tender initialization, payment duplicate-click guard and existing anonymous retail flow.
- **F1 remains open**, not yet certified: exact-head CI must pass; scanner burst/replay with real devices, checkout end-to-end across tender types, physical printer/receipt, cashier PIN handoff, two concurrent registers and responsive browser checks require acceptance. Do not claim full completion until these are evidenced.

### F1 phase transition status — 16 October 2026

- **F1 implementation batch complete / moved to F2**, covering the previously coded anonymous cashier lane, scan/PLU and basket actions, existing checkout/payment/receipt flow, holds, cashier workstations, and the latest payment UI double-submit guard. This is a **development-stage transition**, not hardware or production certification.
- **Release verification remains open:** exact-head GitHub Actions run `38941434214` was still running at transition check; no pass is claimed. Two tills under PostgreSQL concurrency, PIN handoff end-to-end, actual scanner/printer devices, and desktop/mobile browser acceptance have not been witnessed and remain release gates.
- **Next active delivery batch: F2 — catalog, pricing and fiscal correctness**. F1 checkout follow-ups must remain visible in the original checklist and final release acceptance; do not falsely convert SM-11 or SM-33 to full verification without evidence.

### F2 start — owner bulk-price safeguard

- An explicit checkbox is now required both in the catalog import UI and server-side before applying bulk base-price changes. Preview and catalog creation do not require this confirmation; stale-price, tenant-scope, SKU uniqueness and audit validations remain in force.
- Added a regression check for both the visible confirmation control and backend enforcement. **F2 is active and not yet complete**: fiscal receipt calculations, tax/refund precision, labels and complete catalog UX remain subject to tests and acceptance.

### F2 retail refund numeric safety — 16 October 2026

- Hardened the existing `refund_retail_line` domain service so return quantities and money amounts are finite, positive and within their three-/two-decimal database precision before any order, cash, loyalty or inventory records are changed.
- Added parameterized regression cases for NaN, infinity, negative and over-precision amounts and quantities. No duplicate refund service was introduced.
- F2 remains in progress: real tax/refund allocation, fiscal receipt acceptance, printable shelf labels, complete import/upsert policy and external integration/browser verification remain separate gates. Exact-head CI must pass before crediting full verification.

### F2 software handoff / F3 activation — 16 October 2026

- Delivered the existing guarded product create/import/export and bulk base-price review/apply workflow; added server-side acknowledgement of changed prices. Retail returns now validate decimal money and quantities and cap a proposed **partial-line refund** by the original historical discounted line subtotal plus recorded line tax, proportioned by returned quantity. The separate payment-ledger refund cap still applies.
- Added a targeted over-refund regression test alongside malformed-value tests. **Exact-head CI remains a release gate** and is not yet certified green.
- **F2 software handoff recorded; F3 is the next active engineering batch.** Do not mark F2 as fully accepted: URA EFRIS fiscal integration, physical shelf printers, tax-inclusive policy, per-line allocation of order-level discounts, exchanges, full refund/browser tests and bulk catalog operational throughput have not been independently certified.
- Next F3 priorities: concurrent tills/negative-stock defense, count variance approvals, FEFO/expiry holds, reliable unit conversions and branch transfer discrepancy handling. Reuse the existing stock ledger, batch and receiving services.

### 2026-10-16 — F3 integrity / F4 launch checkpoint

- **F3 implemented increment:** reused the existing inter-outlet stock transfer domain service and added quantity validation before any ledger work (strictly positive, finite, no more than three decimals, bounded to the stock column). New tests assert invalid transfer requests cannot change either branch's inventory or create movements. Existing FEFO outflow now also rejects invalid quantities before any batch lookup, with regression tests.
- **F3 is not accepted complete:** count variance approvals, carton/unit conversions, in-transit reconciliation, PostgreSQL two-till concurrency, handheld count and batch recall hardware/workflow acceptance remain unfinished. They must not be marked verified merely to move forward.
- **F4 started:** supplier payment domain service now preflights amounts (strictly positive, finite, <=2 decimal places) before database work; invalid-input tests guard against unintended supplier finance postings. This builds on existing partial-delivery, supplier invoice and receipt audit work.
- **F5 / F6 started as dependency discovery and acceptance scoping only:** existing manager/exception and responsive retail checkout foundations are retained. Their operational UI, approvals, reporting, offline/privacy and physical hardware work is still outstanding; no feature checkbox changes solely on this planning entry.
- **Release gate:** a passing GitHub Actions run for the *final committed SHA* is required; subsequent PostgreSQL and real-browser/device testing must be separately evidenced.

### F3–F6 grouped implementation checkpoint — 16 October 2026

- **F3 branch transfers:** reject negative, zero, nonfinite, malformed and over-precision transfer quantities before stock movement; regression checks unchanged balances and no movements. Existing FEFO outflow validation remains. The current transfer posts stock immediately at both locations — it is **not** an in-transit dispatch/receipt reconciliation engine, so F3 is **still open**.
- **F4 supplier finance:** validate supplier payment amounts before creating payments or accounting entries, rejecting nonfinite and over-precision money; added input regression cases.
- **F5 manager exception review:** delivery discrepancy records now respect the configured exception review lookback window, alongside the existing tenant/outlet/permission scope.
- **F6 workstation and mobile usability:** inventory transfer screen explains immediate handover/accounting effect, uses touch-sized submit control, accessible status feedback and a client-side second-submit guard. Server-side stock and authorization rules remain authoritative.
- **Research:** Shopify's [transfer fulfillment and receiving](https://help.shopify.com/en/manual/sell-in-person/shopify-pos/inventory-management/fulfilling-and-receiving-transfers) separates dispatch, in-transit tracking and destination verification; the current direct-transfer implementation does not yet provide this full multi-stage workflow.
- **Acceptance:** CI on final SHA, PostgreSQL concurrent till/stocktake testing, audit/variance approvals, complete F4 settlement matching, F5 management reports and F6 real devices/offline/hardware remain unverified. No broad F3/F4/F5/F6 completion claim has been made.

### F4 recorded-invoice settlement ceiling — 16 October 2026

- Kept the existing receipt-backed settlement service but added an unpaid-invoice ceiling **when supplier invoices have been recorded**. Payments cannot exceed either received/known-cost value or the outstanding invoiced amount; invoice-free historical receipt-based settlement remains compatible. Payment audit/accounting still posts only on actual settlement.
- Updated the existing staff PO detail screen to show recorded invoice balance, restrict the payment amount to the backend-authorized limit, explain why settlement is blocked once recorded invoices are paid, and prevent rapid double-click submissions in the browser. The server-side idempotency key remains authoritative.
- Added tests for invoice-limited payments and the invoice-free compatibility path. Research baseline: Odoo received-quantity vendor-bill and three-way matching guidance (https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/manage.html). This is a guarded **partial matching step**, not a completed vendor credit-note, PO price variance or full 3-way reconciliation flow.
- Release and UI/browser/PostgreSQL acceptance remain pending until the new exact-commit CI and external verification are available.

### F5 supplier manager insight — 16 October 2026

- Expanded the **existing** supplier balances report with three distinct, scope-filtered figures: unpaid received-goods value, unpaid recorded-invoice value and received-goods value awaiting invoices. The report deliberately does not invent an allocation of purchase-order payments to individual invoice dates; that reconciliation still requires explicit invoice-linked settlement records.
- Updated the staff-facing report labels/columns and regression assertions. The current amount is a read-only decision aid, not new accounting postings, full credit-note capability or a completed margin/drill-down package. Exact-head automated CI, production PostgreSQL and mobile/browser acceptance remain separate gates.
