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
