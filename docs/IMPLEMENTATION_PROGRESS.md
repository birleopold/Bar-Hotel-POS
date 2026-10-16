# Bar–Hotel–Retail suite — live implementation progress board

**Last reviewed:** 16 October 2026  
**Authoritative acceptance and chronological evidence:** [Full 34-phase checklist](SUITE_IMPLEMENTATION_TODO.md)  
**Required supermarket workstream:** [Supermarket checklist — 36 capabilities](SUPERMARKET_IMPLEMENTATION_CHECKLIST.md)

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
| 07 Inventory intelligence | [-] | Planning views, movement-based analysis | Reorder lead times, costing, counting and multi-pack accuracy | SM-08, SM-17, SM-19, SM-26 |
| 08 Batch/expiry/FEFO | [-] | Batch visibility, holds and waste | Atomic FEFO, recalls, expiry sale-block and legacy handling | SM-09, SM-18 |
| 09 Purchasing journey | [-] | PO, receiving, supplier exposure | Requisition, quote comparison, 3-way match, credits, vendor lead time | SM-10, SM-16, SM-31, SM-36 |
| 10 Business date | [-] | Business-day/timezone infrastructure | Consistent boundaries in all reports, shifts and DST tests | SM-29 |
| 11 Hotel night audit | [-] | Nightly folio operations | Full property close and reconciliation | — |
| 12 Housekeeping | [-] | Housekeeping board and staff actions | Mobile and cross-role real workflow certification | — |
| 13 Kitchen display | [-] | KDS state/service UI | Routing and device-level timing/interaction evidence | — |
| 14 Events journey | [-] | Bookings, quotes, payments | Full package, settlement and invoice workflow | — |
| 15 Hardware | [-] | Workstation configuration, receipt/scanner hooks | Supported barcode printer, scale and customer-display adapters | SM-03, SM-12, SM-15, SM-28 |
| 16 Offline | [-] | Offline queue, replay and conflict basics | Retail till offline safety policy and privacy | SM-21 |
| 17 EFRIS | [-] | Fiscal outbox, status and bounded retries | Provider-certified format, reference checks and URA sandbox proof | SM-13 |
| 18 Analytics | [-] | Sales overview, management reports | Real cost/margin, shift drilldowns, supplier and basket analytics | SM-19, SM-29, SM-35 |
| 19 Scheduled reports | [-] | Daily/weekly/monthly email reports | Delivery diagnostics and calendar/provider proof | SM-29 |
| 20 Capability permissions | [-] | Inventory/purchasing capability policy | Consistent POS/finance/hotel API-service checks | SM-20 |
| 21 Manager approvals | [-] | Manager action eligibility | Exact action PIN, different approver, expiry and one-time audit | SM-20, SM-35 |
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
