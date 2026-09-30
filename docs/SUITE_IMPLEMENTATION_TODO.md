# Full suite implementation checklist

Authoritative execution plan · requested 30 September 2026.

## Rules to follow at every checkpoint

- Inspect current code, services, UI, API and audit before each item. Extend existing functionality; never introduce a second implementation of the same operation.
- Deliver complete user journeys including permissions, tenant/outlet scope, validation, audit attribution, migrations, UI, API where applicable, and meaningful regression tests.
- Preserve the Django modular monolith, template-first interface and shared domain services. Target the actual direct-VPS deployment.
- Do not mark a feature complete because a model or page exists. Record implementation and verification separately. PostgreSQL, browser, hardware and provider evidence must be truthful.
- Run required checks before committing ready work to origin main. Update this document in the same commit. Continue the next unchecked dependency; do not forget later stages.
- Historical financial data requires read-only reconciliation and an explicit correction policy; do not silently backfill money or stock.

Status: `[ ]` pending, `[-]` implementation underway, `[x]` implemented and locally verified. External certification remains separately tracked.

## Foundation and operational workspaces

- [x] **01 Workstations/registers/devices:** named, tenant/outlet-scoped device registry; device code; enable/disable; browser selection/pairing/revocation; worker + register + outlet shift ownership; last contact; printer/drawer/KDS configuration; till-by-till payment/refund attribution and reconciliation; migration policy for outlet-only shifts; concurrent open/close checks.
- [-] **02 Role workspaces:** waiter Floor/Open tables/New order/My orders/Lock; cashier Checkout/Active orders/Returns/Register/Lock; reception Arrivals/Departures/In-house/Rooms/New reservation; storekeeper Receive/Transfers/Counts/Low stock/Purchase orders; manager Today/Exceptions/Approvals/Team/Reports. Complete cross-screen journeys and role-filtered navigation.
- [ ] **03 Manager exception centre:** linked cash variances, high refunds, discounts, voids, stock adjustments, low stock, delivery discrepancies, overdue departures, EFRIS failures, offline conflicts and failed PIN attempts; configurable thresholds; resolution history and scoped access.
- [ ] **04 Shift handover:** float, cash sales/refunds, paid outs/drops, independent count, variance explanation, manager approval and next-cashier acceptance; immutable attribution and reconciled cash ledger.
- [ ] **05 Unified customer/guest:** shared identity and contact details across stays, POS, retail and events; merge/deduplicate safely; history, preferences, spend, credit and invoices; privacy and tenant scope.
- [ ] **06 Loyalty/customer account:** shared points ledger, rewards, tiers, birthday/visit/spend offers, coupons and customer discounts; accrual/redemption/reversal idempotency, refund handling and staff UI.

## Stock and purchasing

- [ ] **07 Inventory intelligence:** aging 0–30/31–60/61–90/90+, dead stock, sell-through, consumption velocity, days remaining, supplier lead time/safety stock reorder recommendations; explain data limitations.
- [ ] **08 Batch/expiry/FEFO:** receiving batches, expiry/quantity tracking, earliest-expiry consumption, waste, transfers, returns, recall and legacy stock migration; expired stock policy and concurrency.
- [ ] **09 Purchasing journey:** low stock → suggested reorder → request → quotation → PO → partial delivery → GRN/discrepancy → invoice/payable → payment/credit note → closure; supplier balances, due/overdue, spend, price changes and actual lead time. Reuse current receipt/payment services.

## Hotel, kitchen and events

- [ ] **10 Business date:** tenant/property timezone and configurable closing boundary; agree across shifts, daily sales, reports, restaurant close and night audit; boundary/DST tests and historical policy.
- [ ] **11 Hotel night audit:** open folios, missed arrivals/departures, idempotent nightly room posting, POS room-charge reconciliation, business date close/next date and daily property summary.
- [ ] **12 Housekeeping/mobile:** dirty/cleaning/inspection/ready/maintenance board, assignee, Start/Complete/Inspect, mobile My rooms counts, blocked rooms and scoped actions.
- [ ] **13 KDS/production:** new/accepted/preparing/ready/served transitions, timers, overdue alerts, kitchen/bar station routing, recall, item state/priority/modifiers/table/customer, sound preference and fullscreen touch UI.
- [ ] **14 Events:** lead → quotation → booking → deposit → package/services/menu/room allocation → delivery → final invoice → settlement, unified customer account and reservation conflict checks.

## Hardware, offline and integrations

- [ ] **15 Hardware service layer:** workstation receipt/kitchen printers, scanner, drawer, customer display and scale; device configuration/test workflow; receipt format/routing/retry; adapter boundary and real-device evidence.
- [ ] **16 Offline operating policy/UI:** online/offline, queued count, last sync, synced/waiting/review/failed; retries/conflict resolution, queue age/value limits, allowed tenders, inventory/stale catalog policy, device identity, worker handoff and shared-terminal privacy.
- [ ] **17 EFRIS:** fiscal queue, submission/accept/reject/reference, safe retry/correction and failure dashboard; credential and sandbox evidence; externally required synchronous behavior must follow verified requirements.

## Management, permissions and discovery

- [ ] **18 Executive analytics:** today/yesterday/week/month/custom, revenue, gross profit/cost quality, transactions/basket, occupancy/RevPAR, refunds/discounts/variance, top items, low stock, supplier payables and guest folios; group → branch → outlet → register → employee → transaction drilldown.
- [ ] **19 Scheduled owner reports:** configurable daily/weekly/monthly timezone schedules, email and PDF, scoped recipients, retry/deduplication and delivery history; optional messaging only after supported integration exists.
- [ ] **20 Capability permissions:** extend existing policy layer with sale/discount/refund/void/reopen, inventory view/adjust/transfer, check-in/rate override, finance view/expense and staff manage; role presets, UI/service/API parity.
- [ ] **21 Approval workflows:** request → authorized manager PIN → exact action → audit for discounts/refunds/voids/write-offs/reopens/settled changes/withdrawals/price overrides; expiry, scoped approver, replay and segregation rules.
- [ ] **22 Owner-readable audit:** actor/time/action/value/before→after/reason/approver and linked entity; filter/export, scoped visibility, sensitive-data redaction.
- [ ] **23 UI density:** accessible Floor touch controls and Office dense tables using shared tokens; persisted preference; responsive widths, focus, scroll and touch target evidence.
- [ ] **24 Command palette:** Ctrl/Cmd+K, keyboard navigation, authorized actions and entity lookup; order, reservation, guest/customer, stock, supplier/PO, room, employee and receipt.
- [ ] **25 Global search:** one scoped search for order/receipt/guest/reservation/room/customer/item/barcode/supplier/PO/employee; pagination, useful result labels, permission checks and query limits. Reuse the command palette search backend.
- [ ] **26 Notifications:** read/unread, priority and links for stock, approvals, maintenance, deliveries, cancellations, variances, offline conflicts, fiscal failures and subscription issues; per-user/outlet scope and deduplication.

## Commercial readiness and engineering evidence

- [ ] **27 Onboarding:** business type → details → branch/outlets → catalog add/import → invite staff → configure/test device → test sale → go live, resumable checklist without Django admin.
- [ ] **28 Demo/training:** populated Hotel/Bar/Restaurant/Supermarket demos, isolated tenant/training data and explicit mode, safe reset and no live provider side effects.
- [ ] **29 Subscription entitlements:** consistent template/view/service/API enforcement, sensible disabled-module behavior, tenant isolation and module bypass regression tests.
- [-] **30 Documentation/feature matrix:** reconcile README/product plan/audit with source; generated capability matrix separating backend/UI/API/tests/PostgreSQL/browser/hardware; no stale test counts or claims of certification.
- [ ] **31 Release certification command:** commit-bound evidence for migrations, checks, tests, PostgreSQL/concurrency/RLS, schema, security, browser workflows, static files and rollback review; certificate with actual database/browser versions and timestamp; fail on absent mandatory evidence.
- [ ] **32 Financial/historical policies:** review positive-only historical POS folios and legacy receiving expenses; recipe recovery policy; discounted/taxed split-tender return allocation; no duplicate stock/cash posting; linked-return amount validation and authorized corrections.
- [ ] **33 Deployment/operations:** direct-VPS instructions, database backup/restore drill, worker/scheduler health, rollback, static assets, observability and successful exact-commit release verification.
- [ ] **34 Commercial source policy:** document repository visibility and proprietary-license choices for the owner; do not silently change repository visibility or grant a license. Track the actual chosen policy.

## Excluded as recommended

Microservices, React rewrite, Kubernetes, unrelated AI features, cryptocurrency, full ERP accounting, premature native mobile apps, rebuilding working domains, duplicate API/UI service logic. Container infrastructure is not an assumed requirement for this direct-VPS project.

## Existing foundations to preserve

PIN enrollment/lockout/revocation/idle lock, roles/outlet scoping, modular apps, shared catalog/stock/payments, API and staff service reuse, idempotent settlements, register cash-refund reconciliation, linked retail return/refund, supplier receiving/payment separation, POS room charge and folio settlement, offline replay and optional PostgreSQL RLS. These are inputs to improvement, not reasons to claim later checklist items finished.

## Checkpoint evidence

### 2026-09-30 — start

Baseline `afcf465` on main. Reviewed current register, PIN, outlet scope and audit. Register cash remains outlet-based; multiple simultaneous tills require explicit payment/refund attribution before per-till totals can be trusted. No historical data is rewritten. All unchecked work remains required.

### Workstation checkpoint — implemented, not the whole phase

- [x] Named tenant/outlet workstation registry with unique normalized code and active state.
- [x] Owner/admin create/edit screen; authorized staff list/select/clear actions and navigation from register/office sidebar.
- [x] Signed browser selection survives worker lock/handoff; current tenant/outlet/active membership always rechecked.
- [x] Optional workstation link and opening-worker attribution on new shifts; existing shifts remain intact.
- [x] Reject moving/disabling a workstation with an open shift; preserve outlet-level open-shift locking.
- [x] Audited create/update/selection; throttled last-contact timestamp; optional PostgreSQL RLS migration.
- [x] Printer/drawer/KDS labels are stored and shown honestly as configuration, not active hardware integrations.
- [x] Payment/refund attribution, multiple named tills, per-till cash calculation and idempotent replay.
- [ ] Drawer movement ledger, cash drops/payouts and formal handover — retained in item 04.
- [x] Password-approved browser pairing, scoped approval history, expiry and revocation.
- [ ] Hardware adapters, printer routing and device tests — retained in item 15.
- [ ] PostgreSQL workstation/concurrent shift evidence, browser widths and physical devices.

Verification: full local SQLite suite **278 passed, 2 PostgreSQL-only skipped**. Seven added regressions cover scope/roles, duplicate device codes, signed selection, worker handoff, shift linkage, active-shift edit protection and service scope. Django check and migration consistency pass. New migrations also passed apply → reverse to 0010 → reapply on a disposable SQLite database. Visual browser, PostgreSQL and hardware certification are not claimed. README count and obsolete PIN/modifier statements in the historical product plan were corrected; generated feature matrix remains outstanding.

Checkpoint dependency at that time: browser pairing/revocation. This is now complete below. Cash movement/handover and hardware implementation remain required under items 04 and 15 respectively; neither is included in the completed device registry boundary.

### Register attribution checkpoint — 2026-09-30

New payments/refunds carry protected, nullable shift links. Staff, API, linked returns and offline processing share the existing settlement services and register resolver. Named tills can run separate shifts in one outlet; their cash summaries use only their own received payments and paid-out refunds. Replays preserve original links, including after close, and reject another specified register. Unspecified requests choose only an unambiguous open shift; integrations with no open shift retain unassigned behavior. Legacy and section-wide shifts block simultaneous named tills until closed.

Staff register/checkout/refund screens now identify the selected device; the register page lists other open tills and closes only its selected register. Linked-return history shows the refund till. The read-only `/api/v1/pos/shifts/` endpoint lets authorized clients capture the original shift ID. The OpenAPI export now documents request bodies, idempotency headers and payment/refund/linked-return response contracts.

Offline payments in workstation sections require original `shift_id`; new tenders for closed shifts are rejected for review. No complete persisted offline conflict workflow is claimed. Migration 0013 preserves old shift cash mode/amounts and leaves historical links unassigned. A disposable database probe confirmed old mode preservation, new-mode default, reverse and reapply. Backups are necessary for rollback after live attributed transactions.

Verification: **290 passed, 5 PostgreSQL-only skipped** on SQLite. Twelve added attribution regressions cover concurrent-device accounting, refund drawer, tender exclusion, ambiguous/missing/disabled/closed register rollback, legacy totals, replay after close, linked-return rollback/attribution, API outlet scope, staff close scope and offline origin checks. Three added PostgreSQL-only races cover same-device open, different-device open and payment-versus-close. These tests still need a real PostgreSQL run; browser widths and physical cash/device validation remain external gates.

### Phase 01 implementation complete; Phase 02 underway — 2026-09-30

Current phase: **02 Role workspaces**. The original roadmap remains the organizing intent; the numbered 34-item checklist expands its scope. Phase 01 means device identity/configuration, browser approval/revocation, worker/register/outlet shift linkage and correct per-register money attribution. Formal handover and hardware drivers remain their own later work items (04 and 15); no scope is discarded by advancing.

- [x] Full-password owner/admin device administration and password-confirmed browser approvals. New staff-created stations default to requiring approval; existing stations retain compatible opt-in behavior.
- [x] Thirty-day signed HttpOnly browser credential; only its hash is stored. Approved browser identity survives worker PIN handoff without granting extra worker permissions.
- [x] Scoped approval list, remote revocation with reason/actor, local detach, expiry and tamper rejection. Disabling or moving a station revokes its approvals; open shifts prevent unsafe policy changes.
- [x] Revoked/expired approvals invalidate their PIN session on the next request and block terminal unlock. Required-pairing sections reject staff register/payment/refund attempts without approved selection. Authenticated API clients keep their existing account authorization and register attribution contract.
- [x] Phase 02 floor shortcuts: Floor, Active orders, New order, My orders and Register. My orders respects worker, tenant and outlet scope; search/status/pagination retain that filter. Existing lock control remains available.
- [x] Phase 02 reception shortcuts: Arrivals, Departures, In-house, Rooms and New reservation. Arrival queue includes today's held/confirmed stays; departures include checked-in stays due today or overdue. In-house includes all checked-in stays. All lanes retain branch scope and status filters; empty states describe the actual filter.
- [x] New-order dashboard actions submit CSRF-protected POST. GET navigation no longer creates an order. Existing domain service handles creation.
- [x] Dashboard overflow actions now remain visible rather than being accidentally discarded as duplicates.
- [ ] Finish cashier-specific task emphasis, storekeeper receiving/transfer/count/low-stock journeys and manager workspace links as their dependencies become available. Complete responsive cross-screen evidence for all roles.
- [ ] Phase 01 external gates: run PostgreSQL concurrency/RLS tests against a non-superuser tenant-scoped connection, inspect real browser widths and validate actual deployment/device behavior. Browser automation package is present locally but its Chromium executable is absent; no visual certification is claimed.

Verification: full local SQLite suite **298 passed, 5 PostgreSQL-only skipped**. Eight added regressions cover pairing permissions/password checks, hashing/cookies/audit, expiry/tampering/detach, PIN handoff/revocation, policy edits and cross-tenant isolation, plus floor creation/filter scope and reception date/status/branch queues. Django system check, migration consistency and diff whitespace checks pass. Migrations 0014/0015 passed apply → reverse to 0013 → reapply on a disposable SQLite database; legacy stations retain optional approval. Reversal deletes approval records, so reapproval is necessary after a rollback/reapply. PostgreSQL RLS behavior remains unverified.

Next work: continue item 02, then item 03 exception centre. Preserve every unchecked item above and gather external evidence before any production certification claim.

### Phase 02 — retail and stock workspaces — 2026-09-30

- [x] Retail/supermarket sections show Checkout, Active orders, Returns, Register and Lock for existing server-role staff. No new cashier role or parallel permissions engine is introduced. Switching back to hospitality restores the floor workspace.
- [x] Checkout and Lock are CSRF-protected POST tasks. Returns opens the original closed-receipt search and explains manager authorization; existing linked-return/refund permissions and services remain authoritative. Search/pagination retain the returns task.
- [x] Storekeepers see Receive, Transfers, Counts, Low stock and Purchase orders, restricted to enabled modules. Transfers/counts/low stock reuse existing scoped screens.
- [x] Receiving queue shows sent and partially received purchase orders only, scoped to the worker's selected/accessible outlets. Status filters and pagination retain the queue; the delivery link opens the existing receiving detail workflow. Draft, cancelled, fully received and out-of-scope orders are excluded.
- [x] Role/section workspace headings and consistent task-button styling/focus treatment using the existing theme.
- [x] Supplemental dashboard links now use the same module/visibility gate as primary actions. Read-only accountants keep view links without creation shortcuts; overflowing view actions remain accessible.
- [ ] Phase 02 remaining: manager Today/Exceptions/Approvals/Team/Reports journeys, including item 03 exception-centre and item 21 approval-workflow dependencies; responsive real-browser review for all role journeys. Do not mark item 02 complete yet.

Verification: **301 passed, 5 PostgreSQL-only skipped** on SQLite. Three added regressions cover retail checkout/returns/lock behavior, storekeeper receiving/partial-order/outlet scope and working task targets, and disabled-module/read-only supplemental action filtering. The five role-workspace tests pass together. Django checks and migration consistency pass; no new migrations. Browser and PostgreSQL certification remain pending.

Next dependency: continue management workspace and exception-centre implementation, reusing existing operational snapshots, audit and refund policies. Keep all other unchecked work required.
