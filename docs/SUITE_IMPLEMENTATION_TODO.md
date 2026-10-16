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
- [x] **02 Role workspaces:** waiter Floor/Open tables/New order/My orders/Lock; cashier Checkout/Active orders/Returns/Register/Lock; reception Arrivals/Departures/In-house/Rooms/New reservation; storekeeper Receive/Transfers/Counts/Low stock/Purchase orders; manager Today/Exceptions/Approvals/Team/Reports. Complete cross-screen journeys and role-filtered navigation.
- [x] **03 Manager exception centre:** linked cash variances, high refunds, discounts, voids, stock adjustments, low stock, delivery discrepancies, overdue departures, EFRIS failures, offline conflicts and failed PIN attempts; configurable thresholds; resolution history and scoped access.
- [x] **04 Shift handover:** float, cash sales/refunds, paid outs/drops, independent count, variance explanation, manager approval and next-cashier acceptance; immutable attribution and reconciled cash ledger.
- [-] **05 Unified customer/guest:** shared identity and contact details across stays, POS, retail and events; merge/deduplicate safely; history, preferences, spend, credit and invoices; privacy and tenant scope.
- [-] **06 Loyalty/customer account:** shared points ledger, rewards, tiers, birthday/visit/spend offers, coupons and customer discounts; accrual/redemption/reversal idempotency, refund handling and staff UI.

## Stock and purchasing

- [-] **07 Inventory intelligence:** aging 0–30/31–60/61–90/90+, dead stock, sell-through, consumption velocity, days remaining, supplier lead time/safety stock reorder recommendations; explain data limitations.
- [-] **08 Batch/expiry/FEFO:** receiving batches, expiry/quantity tracking, earliest-expiry consumption, waste, transfers, returns, recall and legacy stock migration; expired stock policy and concurrency.
- [-] **09 Purchasing journey:** low stock → suggested reorder → request → quotation → PO → partial delivery → GRN/discrepancy → invoice/payable → payment/credit note → closure; supplier balances, due/overdue, spend, price changes and actual lead time. Reuse current receipt/payment services.

## Hotel, kitchen and events

- [-] **10 Business date:** tenant/property timezone and configurable closing boundary; agree across shifts, daily sales, reports, restaurant close and night audit; boundary/DST tests and historical policy.
- [-] **11 Hotel night audit:** open folios, missed arrivals/departures, idempotent nightly room posting, POS room-charge reconciliation, business date close/next date and daily property summary.
- [-] **12 Housekeeping/mobile:** dirty/cleaning/inspection/ready/maintenance board, assignee, Start/Complete/Inspect, mobile My rooms counts, blocked rooms and scoped actions.
- [-] **13 KDS/production:** new/accepted/preparing/ready/served transitions, timers, overdue alerts, kitchen/bar station routing, recall, item state/priority/modifiers/table/customer, sound preference and fullscreen touch UI.
- [-] **14 Events:** lead → quotation → booking → deposit → package/services/menu/room allocation → delivery → final invoice → settlement, unified customer account and reservation conflict checks.

## Hardware, offline and integrations

- [-] **15 Hardware service layer:** workstation receipt/kitchen printers, scanner, drawer, customer display and scale; device configuration/test workflow; receipt format/routing/retry; adapter boundary and real-device evidence.
- [-] **16 Offline operating policy/UI:** online/offline, queued count, last sync, synced/waiting/review/failed; retries/conflict resolution, queue age/value limits, allowed tenders, inventory/stale catalog policy, device identity, worker handoff and shared-terminal privacy.
- [-] **17 EFRIS:** fiscal queue, submission/accept/reject/reference, safe retry/correction and failure dashboard; credential and sandbox evidence; externally required synchronous behavior must follow verified requirements.

## Management, permissions and discovery

- [-] **18 Executive analytics:** today/yesterday/week/month/custom, revenue, gross profit/cost quality, transactions/basket, occupancy/RevPAR, refunds/discounts/variance, top items, low stock, supplier payables and guest folios; group → branch → outlet → register → employee → transaction drilldown.
- [-] **19 Scheduled owner reports:** configurable daily/weekly/monthly timezone schedules, email and PDF, scoped recipients, retry/deduplication and delivery history; optional messaging only after supported integration exists.
- [-] **20 Capability permissions:** extend existing policy layer with sale/discount/refund/void/reopen, inventory view/adjust/transfer, check-in/rate override, finance view/expense and staff manage; role presets, UI/service/API parity.
- [ ] **21 Approval workflows:** request → authorized manager PIN → exact action → audit for discounts/refunds/voids/write-offs/reopens/settled changes/withdrawals/price overrides; expiry, scoped approver, replay and segregation rules.
- [-] **22 Owner-readable audit:** actor/time/action/value/before→after/reason/approver and linked entity; filter/export, scoped visibility, sensitive-data redaction.
- [-] **23 UI density:** accessible Floor touch controls and Office dense tables using shared tokens; persisted preference; responsive widths, focus, scroll and touch target evidence.
- [-] **24 Command palette:** Ctrl/Cmd+K, keyboard navigation, authorized actions and entity lookup; order, reservation, guest/customer, stock, supplier/PO, room, employee and receipt.
- [-] **25 Global search:** one scoped search for order/receipt/guest/reservation/room/customer/item/barcode/supplier/PO/employee; pagination, useful result labels, permission checks and query limits. Reuse the command palette search backend.
- [-] **26 Notifications:** read/unread, priority and links for stock, approvals, maintenance, deliveries, cancellations, variances, offline conflicts, fiscal failures and subscription issues; per-user/outlet scope and deduplication.

## Commercial readiness and engineering evidence

- [-] **27 Onboarding:** business type → details → branch/outlets → catalog add/import → invite staff → configure/test device → test sale → go live, resumable checklist without Django admin.
- [ ] **28 Demo/training:** populated Hotel/Bar/Restaurant/Supermarket demos, isolated tenant/training data and explicit mode, safe reset and no live provider side effects.
- [ ] **29 Subscription entitlements:** consistent template/view/service/API enforcement, sensible disabled-module behavior, tenant isolation and module bypass regression tests.
- [-] **30 Documentation/feature matrix:** reconcile README/product plan/audit with source; generated capability matrix separating backend/UI/API/tests/PostgreSQL/browser/hardware; no stale test counts or claims of certification.
- [-] **31 Release certification command:** commit-bound evidence for migrations, checks, tests, PostgreSQL/concurrency/RLS, schema, security, browser workflows, static files and rollback review; certificate with actual database/browser versions and timestamp; fail on absent mandatory evidence.
- [ ] **32 Financial/historical policies:** review positive-only historical POS folios and legacy receiving expenses; recipe recovery policy; discounted/taxed split-tender return allocation; no duplicate stock/cash posting; linked-return amount validation and authorized corrections.
- [ ] **33 Deployment/operations:** direct-VPS instructions, database backup/restore drill, worker/scheduler health, rollback, static assets, observability and successful exact-commit release verification.
- [-] **34 Commercial source policy:** document repository visibility and proprietary-license choices for the owner; do not silently change repository visibility or grant a license. Track the actual chosen policy.

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

### Phase 02 implementation complete; Phase 03 underway — 2026-09-30

Current phase: **03 Manager exception centre**. Item 02's role-specific operational entry points are implemented and locally verified. Real-browser/responsive certification remains a separate gate, and the formal request → manager PIN → exact action workflow remains item 21. The Approvals destination opens actual scoped transactions for the existing authorized refund/discount/void actions; it is an action workspace, not a claimed pending-request queue.

- [x] Manager Today/Exceptions/Approvals/Team/Reports shortcuts, shared workspace navigation and active-task indicators. Today links to the exact-date sales report and existing scoped operational snapshots.
- [x] Approvals lists the latest 50 authorized open/closed receipts and opens their existing transaction actions. Team shows up to 100 active workers with matching branch/outlet/role-type scope, including property-only sites; owners/admins can reach existing worker administration. Reports link only permitted, enabled areas.
- [x] Discovered and fixed an existing financial isolation defect: staff HTML/CSV sales in All sections now restrict payment/refund aggregates to accessible outlets. Dashboard sales caches include the accessible-outlet set, preventing reuse of a broader manager's cached totals. Shared report logic is extended rather than duplicated.
- [x] Phase 03 initial live sources: closed-shift positive/negative cash differences, qualifying refunds, tracked low stock and overdue checked-in departures. Module, business-line, tenant, branch/outlet and management-role scope are enforced. Specific cash-variance links open a protected read-only reconciliation record, including in All sections mode.
- [x] Owner/admin configuration of nonnegative cash/refund thresholds and 1–365-day financial lookback, with audit and full-password-session guard. Defaults flag any cash difference and all refunds. Refund thresholds use original recorded currency without conversion; current stock and overdue stays have no age limit.
- [x] Audited manager assessment/reopen notes with version-bound source fingerprints, immutable audit history and identical-post idempotency. Changed source data becomes unreviewed again; stale/out-of-scope/expired source submissions are rejected. Source-specific validation works beyond the display cap.
- [x] Bounded UI: up to 50 rows per exception category and latest 200 assessments across displayed sources. Reviewing records an assessment and does not post money/stock, grant approval or claim the underlying cause was fixed.
- [ ] Phase 03 remaining sources: discounts/voids, stock adjustments, delivery discrepancies, EFRIS failures, offline conflicts and failed PIN attempts. Extend thresholds and resolution/follow-up journeys with exact source links and scoped history; do not mark item 03 complete yet.
- [ ] External gates remain required: real PostgreSQL concurrency/RLS execution and responsive browser review across all role journeys. Chromium is not installed locally; no browser certification is claimed.

Verification: full SQLite suite **311 passed, 5 PostgreSQL-only skipped**. Ten added management regressions cover role destinations/denial, live category and cross-outlet/tenant isolation, source reconciliation, audited idempotent review/reopen, changed-source fingerprints, policy validation/permissions, module gates, approval/team scope, malformed/hidden source rejection, display caps/lookback, property-only team and report/cache isolation. Django system check/migration consistency and whitespace checks pass. Audit migrations 0002/0003 passed apply → reverse to 0001 → reapply on a disposable SQLite database; existing tenant/audit rows survive. Reversal deletes thresholds and review-state tables, so a backup is needed to preserve their state. PostgreSQL RLS remains unverified.

Next work: finish item 03's remaining anomaly sources and follow-up flow, then proceed to item 04 handover. Keep all unchecked scope and certification gates required.

### Phase 03 complete locally; Phase 04 underway — 2026-09-30

Current phase: **04 Shift handover**. All named exception categories now have scoped live sources: order/line discounts and voids, stock adjustments, receipt discrepancy notes, fiscal submission failures, stale/failed offline queue entries and failed worker PIN events, alongside the original four categories. Thresholds cover discount, adjustment, PIN frequency and offline age. Discrepancy details are recorded during actual receiving, and PIN failures log metadata without secrets. The fiscal view links to protected source records and omits provider payloads.

Exception assessments now support assign/due follow-up, resolved and reopen transitions, retain history when the source clears, link to the originating record and reject stale source versions. Managers see only their scoped cases; the existing permission and module gates apply. A case assessment is operational triage and does not itself reverse a transaction or mark an EFRIS submission accepted. Five focused new management regressions passed alongside the prior ten; PostgreSQL/browser/provider certification remains pending.

Phase 04 now has a per-shift audited cash movement ledger. Authorized opening cashiers and managers can record added float and drops; payouts require a manager. Entries require a reason and replay key, bind to the selected register, block cash removal beyond the expected drawer amount, and survive close as historical entries. The register preview and close command include these movements with cash tenders/refunds; other tills remain isolated. The movement is a physical drawer record, not a finance expense posting. Formal independent counting, variance explanation, manager approval and next-cashier acceptance remain to implement before item 04 can be marked complete.

Verification: full local SQLite suite **317 passed, 5 PostgreSQL-only skipped**. Django system check and migration consistency pass; all migrations applied on a disposable SQLite database. A register regression covers separate till totals, movement replay, excessive drops, wrong-device rejection and a closed shift. PostgreSQL row locking/RLS, responsive browser and provider behavior require independent evidence.

### Phase 04 complete locally — 2026-09-30

The staff register now submits the closing cashier's physical count and requires an explanation for any expected-versus-counted difference. A separate worker records an independent count and explains a changed count. A manager who neither submitted nor verified approves, with an explanation for variance against expected cash. A different incoming cashier confirms the exact verified carry-forward amount; acceptance atomically opens the new shift with that float. The register refuses an ordinary new shift while a handover is pending. Each state change has actor, timestamp, exact amounts and audit record; repeating a transition is rejected. Scoped workstation/outlet and membership checks apply at every step. Historical shifts closed before this workflow remain unchanged.

The physical drawer ledger, refunds and payments feed the expected close amount; counted and verified amounts remain separate. No handover step silently creates a finance expense or repairs a discrepancy. The existing direct close service remains available to older internal integrations; staff close follows the handover process. Before certifying production cash control, review any direct integration using that service and run PostgreSQL locking/RLS and real register/browser trials. Phase 05 unified customer/guest is next.

Verification: **320 passed, 5 PostgreSQL-only skipped** on SQLite. The new service tests cover separate actors, changed counts, variance explanations, role/outlet denial, replay and blocked ordinary opening; the staff test follows four worker sessions through submit, verify, approve and accept. Django check, migration consistency and diff checks pass. POS migrations 0018/0019 applied, reversed to 0017 and reapplied on a disposable SQLite database. Reversal removes handover records, so use a matched backup for a production rollback. PostgreSQL concurrency/RLS and browser evidence remain pending.

### Phase 05 shared identity foundation — 2026-09-30

Current phase: **05 Unified customer/guest**. A tenant-scoped customer record now stores shared name, email, phone, preferences and notes. Authorized staff can search/create/edit a scoped directory and see explicitly linked stays, events, orders and folios in accessible branches/outlets. Stay/event forms accept an optional visible customer; reservation details and POS orders permit explicit audited links, and a reservation's folios carry its link. Historical guest names and transaction totals remain snapshots. No automatic matching or financial backfill is performed.

Owners/admins can merge a confirmed duplicate into an active target, with a required reason, row locking, audit counts and moved explicit links. The merged source is retained; original transaction names remain untouched. Suggestions based on name/contact never merge automatically. New customer-table PostgreSQL RLS is added. Existing records start unlinked and require human review.

Remaining Phase 05: customer-linked API parity where appropriate; practical association/search across outlets; currency-specific paid spend, outstanding folio credit/charges, invoices and privacy/retention controls; cross-site access review, merge correction policy and real-browser/PostgreSQL evidence. Do not mark the phase complete yet. Verification: **323 passed, 5 PostgreSQL-only skipped** on SQLite, plus Django check/migration consistency; customer migrations and dependent links applied, reversed and reapplied on disposable SQLite. PostgreSQL RLS and real-browser evidence remain pending.


### 2026-10-15 — Regional product research and baseline CI gate (research branch)

- Added `docs/REGIONAL_HOSPITALITY_PRODUCT_RESEARCH_2026-10.md` with dated research from URA, Bank of Uganda, PDPO, the Ministry of Tourism, regional revenue authorities, OWASP, and public vendor feature pages. Vendor pages are treated as claims, not independent certification. No product checklist item is marked complete by research alone.
- Added `.github/workflows/quality.yml` to run Django system checks, migration-drift checks, and the automated suite on Python 3.12 using SQLite. This is a fast regression gate only; it does not replace PostgreSQL/RLS/concurrency, browser, hardware, provider, or production release evidence. The workflow still needs a successful run before this gate is considered validated.
- Source review confirmed Phase 05 remains the next product dependency. Before extending customer API access, review `visible_customers()`: its `created_by=user` branch may retain visibility of unlinked customer records after a staff member's site assignment changes. Add explicit tests and resolve the intended policy before expanding exposure.
- The reviewed main baseline was `917aba6` (2026-10-06). At research time there were no checked-in GitHub Actions workflow files or recorded Actions runs.
- The first CI run exposed a host-resolution regression: configured single-label central hosts (notably `testserver` and `localhost`) were passed through tenant FQDN validation, causing broad HTTP 400 failures. The middleware now bypasses tenant DNS validation only for explicitly configured central hosts; unconfigured IP addresses remain rejected. Focused regression tests cover testserver, localhost with port, configured IPv4/IPv6, and an unconfigured IP. The rerun after the host fix reduced the suite from 260 failures to **30 failed, 319 passed, 5 skipped**. Investigation identified a missing `MembershipRole` import in `apps/staff/views_lodging.py`, fixed in this follow-up; remaining permission/scope and test-fixture failures still need investigation. Do not merge until the full suite passes.
- Corrected README validation wording so the 323-pass/5-skip count is explicitly historical and linked the research note and CI workflow. Item 30 remains pending because the generated feature matrix and broader documentation reconciliation are still outstanding.
- No production data or deployment changed. Phase 05 remains the next product dependency; no product checklist item is marked complete by this research checkpoint.

### 2026-10-15 — Owner scope decision: Uganda first

- **Explicitly exclude non-Uganda country readiness** from active research, implementation and release dependencies. Do not implement Kenya eTIMS, Rwanda EBM, Tanzania EFD/EFDMS, foreign-country payment adapters, localization or certifications. Preserve architectural extensibility without building these features now.
- **All other existing 34 roadmap items remain in scope**, especially Uganda EFRIS, MTN MoMo/Airtel Money reconciliation, PDPO privacy controls, financial integrity, POS/hotel/retail workflows, hardware, offline resilience, premium UI, CI, backups and commercial readiness.
- Latest GitHub Actions suite on prior commit `b9cce6e`: **325 passed, 24 failed, 5 skipped**. Do not merge or certify until the remaining failures are addressed. No foreign-country work is a prerequisite.

### 2026-10-15 — Merged implementation checkpoint

- Merged pull request #1 into `main` as `00ebc3489bec7458711c400b92abce09261fffa4`: Uganda-first research/roadmap, GitHub Actions quality gate, central-host regression, outlet-derived branch permissions and customer-visibility restrictions with focused tests.
- Latest completed pull-request CI before merge: **341 passed, 14 failed, 5 skipped**, improved from 325 passed and 24 failed. These 14 failures remain outstanding and must not be represented as passing; verify main CI separately.
- Continue Phase 05 and test stabilization, while retaining all other Uganda-first checklist items. Kenya, Rwanda and Tanzania country-specific adapters remain excluded.

### 2026-10-15 — Phase 05 financial summary implementation

- Added `apps.staff.services.customer_finance.customer_financial_snapshot`: branch/outlet-scoped direct paid POS sales and folio charges/payments/outstanding, separated by currency; POS linked to folio excluded from standalone sales to avoid double counting.
- Added `financial_snapshot` to customer detail view context and a regression test covering scopes, folio-linked orders, and partial payment.
- **Phase 05 is still in progress**: customer API, invoices, complete privacy/retention policy and full UI rendering/verification are not finished; this service is not presented as full accounting or a loyalty ledger. Phase 06 is still pending. No external provider, browser or CI-green evidence is claimed.

### 2026-10-15 — Phase 07 stock coverage verification checkpoint

- Added `backend/tests/test_stock_coverage_snapshot.py` covering scoped inventory sale velocity, daily consumption, stock runway and low-stock thresholds. No stock mutations or purchases are triggered.
- Phase 05–08 remain incomplete: Phase 05 APIs/invoices/retention, Phase 06 reward ledger, Phase 07 operational UI/aging/lead times, Phase 08 batch/expiry/FEFO accounting and migrations require implementation and passing CI. Do not mark them complete based on source commits alone.


### 2026-10-15 — integrated inventory and purchasing implementation

The owner requires non-interactive implementation and a separate later verification pass. Status remains in-progress until the listed features and end-user workflow are complete.

- **Phase 08:** PO receiving now accepts optional batch code and expiry date via staff UI and REST serializer, saves the linked receipt batch, and updates aggregate inventory once. Sales, recipe consumption, manual decreases and transfers now use FEFO for items with recorded batch history while retaining the legacy process for items with no batch history. Batch UI supports hold/release, explicit write-offs (posting both ledgers), and operator-controlled labeling of older counted stock without posting a second receipt. Database migration and PostgreSQL tenant RLS added. Domain regression tests authored.
- **Phase 09:** Existing PO/partial receipt/payment flows retained; repeated delivery references blocked; new staff Supplier balances screen displays received value, actual payment and known unpaid amount, scoped to permitted outlets, with missing cost values flagged. Purchasing navigation links to the screen.
- **Still pending in 08:** returns/restock policy, targeted recall, complete historic batch-reconciliation process, deployment/concurrent PostgreSQL verification, and remaining UI refinements.
- **Still pending in 09:** requests/quotations, supplier invoice and credit-note workflow, invoice reconciliation, supplier lead-time statistics and due-date tracking.
- **Scope:** 34 phases remain the authoritative roadmap; no phase moved to completed on the basis of an unverified partial feature.


### 2026-10-15 — substantial follow-on implementation (verification deferred)

Phase 08 improvements:
- Fixed a sale-stock regression in which the sale loop referred to an undefined recipe ingredient identifier. Recipe ingredients now receive their own FEFO allocation during recipe posting.
- Added `StockBatchAllocation` as a durable stock movement ↔ inventory batch traceability ledger, with database constraints and PostgreSQL tenant isolation. Record allocations for POS sales, recipes, manual decreases/waste, physical-count shrinkage and both sides of transfers.
- Staff batch screen now shows linked movements and order/transfer references. A manager can put matching product+lot records on hold across authorized outlets without silently discarding goods or implying a product recall has been fully resolved. Tests added.
- Lot-level identity and traceability follow the GS1 traceability principles: https://www.gs1.org/standards/gs1-global-traceability-standard/current-standard

Phase 09 improvements:
- Added persisted supplier invoices linked to purchase orders, with invoice numbers, dates, payment deadlines and amounts. Duplicate-replay protection, received-value caps, cost-data checks, tenant/outlet authorization and audit logging are implemented.
- Staff purchase-order detail now offers invoice recording and history; the purchasing API supports invoice recording; supplier balance reporting distinguishes received, invoiced, paid and due date amounts, without inventing a cash payment or assuming invoice-level payment allocation.
- PostgreSQL tenant isolation migration and regression tests added.

Phase 10 started:
- Configurable business-wide time zone and operating-day cutover hour, plus per-property overrides.
- Manager-facing configuration/preview available in the Management workspace, accessible on narrow/wide screens and with scoped edits, audit logs and validation.
- Timezone-aware resolver handles ambiguous daylight-saving instants by converting actual instants to local wall time. Tests added.
- Still required before Phase 10 completion: integration with POS shifts, period reports, hotel night audit, historical-date correction policy and full verification.

Engineering: implementation files committed to origin/main. Automated verification remains a separate pending pass at the owner's request. Django transaction boundaries and PostgreSQL row locking are used in the inventory path; reference: https://docs.djangoproject.com/en/5.2/topics/db/transactions/ .


### 2026-10-15 — Phase 10, 11 and 12 end-user implementation batch

**Phase 10 property operating dates:**
- Added `business_day_window` to map a property's local date and configured closing boundary into timezone-aware reporting timestamps, with daylight-saving tests.
- Sales summary page and CSV exports now offer a visible **Property operating dates** basis in addition to the legacy UTC calendar basis. Multi-property selections are explicitly rejected for that mode instead of pretending different timezones share one business day.
- The hotel night audit now uses the same property-date boundaries to evaluate open till shifts and paid room-charge orders.

**Phase 11 hotel night audit:**
- Added tenant-scoped `PropertyNightAudit` with a unique property/date constraint, PostgreSQL RLS and immutable close snapshot.
- Read-only preview computes occupied rooms, overdue arrivals/departures, open shifts, folio currency totals, missing/duplicate room nights and unmatched paid room-charge orders.
- Single-night recovery posting can fill a missing room line under a transaction and row lock without duplicating a legacy upfront charge. Existing check-in nightly charges now skip already-posted room descriptions.
- The manager-only close requires no live exceptions and explicit reviews of cash and folios, prevents a future-date close, closes sequential dates after the initial close, records attribution and returns the same close on retry. This does **not** fabricate external bank/cash settlement or rewrite prior payment dates.
- The lodging subnavigation exposes **Night audit**, with mobile-responsive review/close controls, archived close history and a CSV summary without guest personal identifiers.
- Regression tests authored for duplicate prevention, rate/folio conditions, date scope, manager confirmations and repeat close.
- **Still incomplete:** automatic scheduled audit, historical corrections/late-entry adjustment policy, payment-provider settlement confirmation, real-browser and PostgreSQL concurrency evidence.

**Phase 12 mobile housekeeping:**
- Extended existing Room status with **Cleaning**, responsible housekeeper, start/finish/inspect timestamps, and append-only RoomHousekeepingEvent history with PostgreSQL RLS.
- Existing Housekeeping page now has **My rooms**, **Unassigned**, and **All rooms** queues; mobile-accessible Claim/Start/Finish/Inspect actions; manager assignment and room availability actions; and scoped activity history.
- Workflows require active staff, tenant/property access, permissions and transactional room locking. Open maintenance blocks completion/inspection/check-in.
- Checkout resets the room to dirty, clears stale assignments, and records the handover event, ready for the next guest.
- Tests authored for assignment, cleaner-only access, manager inspection, maintenance blockers and property isolation.
- **Still incomplete:** scheduled cleaning, configurable mandatory inspection policy, task duration analytics and cross-device browser verification.

**Verification status:** Owner requested implementation before the separate verification pass. All above are committed to `origin/main` but are **not** certified green; this checkpoint does not mark any of these phases complete. Follow the remaining 34-phase roadmap, then run the staged test, browser, PostgreSQL and release checks before production.


### 2026-10-15 — Phases 13 and 14 implementation checkpoint (separate verification later)

**Phase 13 Kitchen & Bar Production**
- Extended the existing KDS line status system with optional **Accepted** while preserving the existing one-tap **Start prep** path. In-prep, ready and served transitions remain in the existing workflow.
- Added persisted **rush** priority, per-line status transition timestamps, and manager-authorized **recall from Ready to In prep** requiring a reason. Existing order locks, station and role scopes and audit logging remain enforced.
- Improved the kitchen/bar staff queue with overdue elapsed-time alerts (initial 15-minute threshold), rush tickets first, modifier details, totals for accepted/rush/overdue items and optional accepted actions. Added a responsive touch-friendly design with accessible button dimensions, fullscreen control and opt-in per-device notification sound.
- Live WebSocket queue refresh now updates summary metrics alongside tickets and recalculates timers; the KDS API exposes rush, modifiers, wait duration and guarded actions. Station classification is shared between API and staff views.
- Backend workflow regression tests authored for status transitions, priority changes, recall and authorization. Layout design referenced: https://squareup.com/help/us/en/article/8168-prioritize-orders-with-square-kds ; https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum .
- Still outstanding before full Phase 13 completion: overdue thresholds configurable by station, production-time analytics, sound accessibility across hardware, ticket-level recall, scheduled/multi-device browser evidence and complete real-time contract certification.

**Phase 14 Events**
- Preserved the existing customer-linked event space and booking system and added tenant-scoped **EventQuote** records (draft/sent/accepted, amount, validity and description) and immutable, idempotent **EventPayment** records (actual amount received, method and reference). Database migrations and PostgreSQL RLS included.
- Added a controlled, audited event journey: create quotation, mark sent, accept quotation under event-space lock and overlapping booking checks, confirm the booking, record customer deposit/settlement and post real money to the cashbook once using the existing finance posting bridge. Planned deposit on the booking remains separate from actual customer payments.
- Extended the existing event detail page with quotes, acceptance, payments, remaining approved balance and edit forms, responsive using existing staff layout. Added corresponding API actions and regression tests for accepted quote, payment replay, conflict, overpayment and cashbook linkage.
- Staff event booking form now blocks conflicting space bookings and prevents direct cancellation when recorded customer payments require financial resolution. No outbound quotation delivery is claimed; **mark sent** is a human confirmation.
- Event payment receipts are **not automatically placed in EFRIS** because deposit tax-point treatment must be verified against applicable Uganda fiscal rules.
- Still outstanding before full Phase 14 completion: service/package itemization and final invoices, equipment/room allocations, event delivery milestones, partial refunds/credit notes, customer communication delivery and full stage/role/browser certification.

Verification deferred at owner's direction. Status is implementation-in-progress rather than released or certified. The authoritative roadmap remains exactly **34 phases**.


### 2026-10-15 — Phase 07 stock intelligence implementation

- Added scoped `apps.inventory.insights.build_stock_intelligence` to analyze recorded sale and recipe consumption over a rolling 30-day interval, actual supplier delivery lead times (up to a one-year sample window), on-hand quantities and explicitly dated batches.
- Age groups cover **0–30**, **31–60**, **61–90**, **over 90 days**, plus **unknown age** for remaining unbatched stock. Reports flag a batch/aggregate quantity disagreement rather than silently treating bad quantities as valid.
- Derived advisory **daily usage**, estimated days of cover, a clearly labeled *indicative movement ratio* rather than a falsely precise formal sell-through rate, cautious idle-stock warnings requiring historical receiving evidence, and restocking suggestions.
- Restocking target uses observed demand × (observed lead time + user-selected days of buffer). If there is no trustworthy delivery history, suggestions fall back to the SKU's explicitly configured reorder level; when neither input exists the UI says there is insufficient information. No fabricated supplier lead times or automatic orders.
- New responsive **Inventory → Stock planning** page with 24-item pagination, low-stock filter, adjustable stock buffer (0–30 days), batch-age breakdown, supplier delivery sample count and explanation of what data is missing. Tenant/outlet filtering respects the active staff section selection.
- Regression tests authored for recorded rolling usage, batch aging, supplier delivery timing, permissions and invalid planning parameters.
- Research: https://stockoutinventory.com/guides/reorder-point-safety-stock (Sept 2026) and https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum .
- Remains in progress until formal sell-through can be reconciled from opening, receipt and return inventories, seasonality and stockout biases are addressed, accessible reporting exports/aggregates are integrated, and owner-deferred verification is completed.


### 2026-10-16 — direct implementation batch: staff discovery, UI, audit, alerts, release evidence

**Phase 22: Management audit explorer (in-progress).**
- Improved the **existing** staff/settings/activity route and activity view rather than duplicating the audit system.
- Added date, event and record-type filters, 40-record pages, a bounded 1,000-record CSV export and actor/action/entity/time details.
- Added server-side redaction for passwords, tokens, PINs, addresses, contact details and sensitive nested fields, plus spreadsheet-formula escaping.
- Restricted owner/admin visibility to their own tenant; other managers see only events whose stored payload contains an assigned site/outlet identifier. Legacy events with no explicit scope fail closed for non-owners. Owner/scope regression tests authored.
- Remaining: normalized audit scope fields for legacy events; semantically formatted before/after financial diffs, broader actor/reason/approver navigation and verified export accessibility.

**Phase 23: Floor and Office layout density (in-progress).**
- A visible header control cycles between **Standard**, **Floor touch** and **Office compact** layouts, remembered by tenant/user on each browser; compact mode retains minimum mobile controls. CSS applies to staff tables, cards, forms and kitchen.
- Remaining: cross-device preference sync and actual keyboard/touch/large-display review before calling complete.

**Phase 24 and 25: Authorized command palette and global search (in-progress).**
- Ctrl/Cmd+K opens an accessible native search dialog from the shared staff shell; Enter/Arrow keys navigate, Escape closes, focus returns to opener. A full-page no-JavaScript search path and responsive search layouts are available.
- A **single** query service scopes order, reservation, room, folio, customer, catalog/SKU/barcode, supplier, purchase order, event and worker records by tenant/member/assigned sites/outlets/entitled modules. The search endpoint bounds input length and rate, uses no-store responses and does not persist guest search terms.
- Full page supports bounded pagination of results by category; frequent records return direct URLs, with targeted filters added to room, menu/catalog, stock-balance and supplier directories. Source data is added to the browser using text nodes (not injected markup). Tests cover tenant, site/outlet, module and customer privacy rules.
- Research: WAI-ARIA 1.2 combobox and keyboard design: https://www.w3.org/WAI/ARIA/apg/patterns/combobox/
- Remaining: unified index for larger datasets, indexing/performance evidence, additional receipt/reference types and cross-browser assistive-technology certification.

**Phase 26: Private staff alerts (in-progress).**
- Added a tenant-isolated persisted `StaffNotification` inbox with unique member/source identity, priorities, read/unread history and tenant RLS.
- A staff-accessible notifications screen allows explicit **Refresh**, **Unread**, **Mark read** and **Mark all read** actions. Refresh derives live low-stock, unresolved room repair and goods-delivery discrepancy alerts in the user's assigned locations and enabled modules; it deactivates resolved source rows instead of deleting audit history. Notification read state never crosses workers or tenants. Header displays unread count.
- No automatic push/SMS or asynchronous producer is claimed. Additional exception types and delivery schedules remain pending.
- Tests authored for location privacy, replay deduplication, user isolation and resolved inventory alerts.

**Phase 31: Fail-closed release evidence command (in-progress).**
- Added `tools/release_certificate.py` and `docs/RELEASE_CERTIFICATION.md`. The command targets an exact clean git commit, executes Django deployment/migration/test/static checks in an isolated staging environment and requires explicit matching PostgreSQL/RLS/concurrency, browser, restore, rollback, and when applicable hardware evidence. Missing or failing mandatory evidence results in FAIL.
- The command **has not been run**, per the owner's deferred verification instructions. Supplied evidence is self-reported and must be corroborated by the release operator.

**Status:** These features have been committed to `origin/main` for implementation progress only. They have not completed CI, database, browser, safety or production certification. The complete remaining 34-phase roadmap is not finished, and phase checkboxes remain in progress until all acceptance items are delivered.


### 2026-10-16 — new user-facing stock, offline, hardware and documentation work

**Phase 08:** Inventory → Batches & expiry now includes direct stock-batch receiving with tenant/outlet/product authorization, duplicate-lot protection, stock-balance locking and one underlying receipt movement. Receipt movements are linked to batch history. Quantities require three-decimal precision; future receipt dates are disallowed; expired-at-receipt stock is placed on hold and cannot be released as saleable stock. Staff can search/filter batches (available/held/expired/expiring), retain filters while paging and export a bounded, spreadsheet-safe CSV. Direct receipt is explicitly separate from purchase-order receiving, which remains the proper supplier-payable path. Tests authored for duplication, stock/lot history, expired quarantine, scope and validation. Missing: linked returns by original lot, full stock-count batch reconciliation and physical recall evidence.

**Phase 15:** Existing Workstations navigation now links to a scoped **Test equipment** page with a nonfinancial browser print slip, local keyboard-wedge barcode scanner diagnostics and honest unsupported-device messages. Retail-only tenants do not see unrelated kitchen printer/KDS controls. No direct printer routing, drawer or scale adapter is claimed, and physical tests are not complete.

**Phase 16:** Existing Offline activity page now distinguishes server-received replay rows from device-local operations not yet delivered; shows waiting/applied/failed/stale counts, last server-applied activity, connection test and safe catalog-conflict guidance. The concurrent origin/main work also contains separate offline safety and manager-review improvements; their exact acceptance and certification are not assumed here. Multi-device offline conflict testing and complete local terminal queue behavior remain outstanding.

**Phase 30:** Added a reproducible source-filename matrix generator and initial `docs/CAPABILITY_MATRIX.md` for all 34 items. These are conservative file-presence signals, not behavioral test claims; no PostgreSQL, browser or hardware result is invented. Run `python tools/generate_capability_matrix.py` whenever the roadmap/source changes. Full source/route/test contract reconciliation is still pending.

**Phase 34:** Added `docs/COMMERCIAL_SOURCE_POLICY.md` explaining current absence of a root license, public-source copyright, distribution options, dependency licensing and contract decisions. Neither a new license nor a repository-visibility change was made. Owner-selected commercial policy remains pending.

**Status:** Implementation committed to origin/main, with verification intentionally deferred per owner's instructions. No assertion of 50% phase completion, passing CI, release certification or live-device readiness.


### 2026-10-16 — Phase 15/16 continuation: physical-device observations and offline sync protection

**Phase 15: Hardware capability boundary and observable checks (still in progress)**
- Reused the existing **Workstations → Test equipment** page, browser print sample, barcode input test and device configuration instead of creating a duplicate hardware system.
- Added an explicit `apps.pos.services.hardware` boundary distinguishing supported browser printing / keyboard-wedge scanning from direct kitchen printer, drawer and scale functions, which remain **unavailable without approved hardware adapters**.
- Added `WorkstationHardwareCheck` records with operator, workstation, tenant, observed device type, outcome, configured device label snapshot and note; append-only observation history and PostgreSQL RLS. Owner/administrator password login is required to save a check. A failure needs a reason, and no test triggers payments, drawer opening or inventory changes.
- The **existing** equipment test page now has a staff-observed check form and recent history; kitchen choices remain hidden when the current section lacks kitchen entitlement. Service and UI regression tests authored.
- Unfinished: physical receipt/kitchen printer adapter implementations, routed retries, actual drawer/scale/customer display integration, approved local drivers and independent real-hardware certification.

**Phase 16: Offline operating policy and manager conflict workflow (still in progress)**
- Patched both single-operation and batch sync APIs to verify staff's authorized **outlet before writing** a rejected stale-catalog queue entry. The audit path rejects a reused ID associated with a different section or operation.
- Hardened request-ID replay across **pending, applied and failed** states. An applied operation cannot be modified; a catalog-stale retry can replace **only** the catalog-version fingerprint with the same ID. Other altered payload content is rejected. Added a 64 KiB server mutation-payload bound.
- The generic browser replay is now **cash-tender only**. Card, mobile money and bank transfers require online provider verification before recording; none can be falsely posted as offline-settled. This follows the cautious provider-specific approach documented in `docs/OFFLINE_POS_POLICY.md`.
- Extended the existing **POS → Offline** staff page with waiting/applied/failed/unreviewed metrics, configurable pending-hour warnings from the existing exception policy, corrected table headings, explicit tender instructions, responsive conflict review forms and retained original request IDs.
- Added manager-only, transactional **Record review** with a required note, reviewer and timestamp. This does not retry, change stock or mark payments paid. The existing notification inbox can surface unreviewed failures and overdue server syncs to appropriately scoped managers.
- Database migration `0022_offline_review` and regression tests authored for rejected electronic tender replay, stale-ID safety, unauthorized outlet stale writes and manager-only review.
- Still unfinished: durable client-side/offline browser queue, authenticated device age limits and total risk limits, per-device worker handoff, background sync attempts, true receipt/provider reconciliation, full offline privacy controls and tested disconnected hardware behavior.
- Research basis: https://squareup.com/help/us/en/article/7777-process-card-payments-with-offline-mode and https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum .

**Verification status:** Owner requested implementation first. Code and tests are committed to `origin/main`; no claim of full CI, PostgreSQL concurrency, offline-browser device or hardware certification is made. The 34-phase completion count remains based on **fully accepted** phases, not partially implemented features.


### 2026-10-16 — Phase 27 guided onboarding and Phase 19 owner reporting (implementation-first batch)

**Phase 27: Guided onboarding (in progress)**
- Extended existing **Console → Workspace setup** rather than introducing parallel onboarding. Existing business-line selection, branch/outlet creation, invitations, inventory, room setup and go-live cards are retained.
- Added required **business type**, **first sellable product/service**, and (for businesses with POS activity) **named workstation** steps. Opening stock is required only when an active SKU actually tracks inventory. Required stages cannot be skipped to fabricate completion; blocked steps remain incomplete.
- Added a resumable checklist progress indicator, direct staff sidebar **Business setup** access for approved admin roles, and links to configuring/testing devices, staff invitations and real first-sale review. Go-live messages now explicitly distinguish automatic setup prerequisites from real device/payment certification.
- Added **Catalog CSV import** with tenant isolation, UTF-8 limits (256 KiB, 250 items), strict rows and amount/quantity validation, category reuse/creation, duplicate SKU/barcode rejection, no partial import and a clear preview action. Stock, cash and fiscal records never change during import. Retail/hospitality catalog importer is not exposed to lodging-only businesses. Responsive import screen, example CSV, staff/console navigation and regression tests added.
- Added a **no-payment checkout rehearsal** with the existing POS pricing/tax and quantity rules, section price overrides and a stored owner/date. It does not create a sale, payment, shift, stock movement or EFRIS document and is clearly labeled a nonfinancial preview. Screen is reachable from setup; tests authored.
- Research references: https://help.shopify.com/en/manual/intro-to-shopify/shopify-pos-launch-checklist and https://support.phppointofsale.com/hc/en-us/articles/53260874229396-Your-first-day-store-setup .
- Remaining: end-to-end safe training tenant/transaction support, proof that an actual configured payment terminal and printer work, opening-day signed decisions, full import browser and PostgreSQL concurrency verification, and additional branch-level onboarding where needed.

**Phase 19: Owner-configurable scheduled sales reporting (in progress)**
- Extended the existing ops digest rather than copying its financial aggregates. Added opt-in `OwnerReportSchedule` by tenant with optional property scope, daily/weekly/monthly cadence, local send-hour/day, and selected active owner/admin membership recipients. Default **off**.
- Added per-period deduplicated `OwnerReportDelivery` history (sending, sent, failed), UTC/business-operating-date scope text, bounded failure retries, 45-minute retry gap and a persistent **Sending** state to prevent automatic SMTP duplicate resends.
- Added PDF overview (ReportLab) plus CSV detail from the existing `build_sales_summary`, no customer-identifying details, and formula-safe CSV free text. Celery beat checks due schedules hourly and restores explicit per-tenant PostgreSQL RLS context between businesses.
- New **Staff → Settings → Owner email reports** page offers owner/admin-only configuration, scoped recipients, preview PDF/CSV downloads and delivery history. PIN-only sessions cannot change email routing. No report emails are sent automatically until owners explicitly enable the schedule and working beat/worker/email services are configured.
- Backend service tests authored for timezone/day rules, opt-in, recipient isolation, SMTP retries, delivery uniqueness and settings page access. Deployment and operational notes: `docs/OWNER_REPORT_SCHEDULING.md`.
- Remaining: staging mail-provider evidence, PDF rendering across fonts and devices, alternate financial KPIs and recipient scope variations, operations monitoring of stuck Sending records, actual time/date and PostgreSQL verification.

**Verification status:** Per owner instruction, staged verification is deferred. The code is committed to `origin/main` but is **not** certified for production. Neither Phase 19 nor Phase 27 is marked fully complete until its remaining acceptance requirements are met.


### 2026-10-16 — Phase 06 loyalty ledger implementation (not phase completion)

- Extended the existing shared customer record with an append-only **LoyaltyLedgerEntry** for whole-point earnings, redemptions, reversals and manual corrections. Added tenant/source uniqueness and nonzero-point constraints, database migrations `0003_loyalty_ledger` and `0004_loyalty_rls`, including PostgreSQL tenant isolation.
- Implemented `apps.customers.loyalty.points_balance` and a transactional, replay-safe manager correction service. Tenant owners/administrators must provide a unique request ID and a documented 12–300 character reason; a correction cannot take the balance below zero.
- The existing **Customers → Profile** page now includes a points balance, the recent point ledger, and an owner-only correction form. The UI explicitly states that these points are not monetary credit and do not yet automatically earn or redeem.
- Regression tests authored covering duplicate requests, insufficient balance, cross-tenant customers and unauthorized staff. These changes have not undergone the owner-deferred verification pass.
- **Still required**: tenant-configured accrual rates, points on fully paid sales, provider/payment-specific refund reversals, purchase reward redemption during checkout, tiers/visit and birthday campaigns, coupons, promotion precedence, merged-customer ledger transfer, API parity, comprehensive reconciliation and end-user browser certification.
- No claims of a fully functioning commercial loyalty program or automatic reward accrual are made.


### 2026-10-16 — Phase 06 continuation: earning, refunds, merging, POS/customer UI

- Workspace owners/admins can now enable future rewards in **Workspace → Branding & defaults → Customer points** and configure how much eligible spending in the workspace default currency is needed for one whole point. The tenant setting defaults to **off** and uses an explicit decimal spend threshold (`tenants.0022_loyalty_policy`).
- Existing **paid POS order** flow (both restaurant and standalone retail) awards points once when an attached customer's **final settlement** completes, excluding tax and order-level discounts and with no exchange-rate assumptions. Partial payments, unlinked orders, zero-point awards, a disabled program, and another currency do not earn. An order-level source key and atomic payment lifecycle prevent duplicate earning.
- The existing POS **refund flow** reverses the original earned points *proportionally* against cumulative refunded sale value, with last-refund rounding reconciliation and unique per-refund source keys. Turning earning off or modifying the earning rate never prevents necessary reversals. A customer whose points were used earlier may have a negative point balance after a legitimate refund; this does **not** block the customer's financial refund.
- Existing **verified customer merge** now transfers immutable point ledger entries with order, folio and booking links. Transaction order locks protect concurrent checkout/refund/merge operations. A closed sale with earned points cannot be silently relinked in the order editor, preventing reward history from becoming detached from the sale.
- Existing **Customers & Guests** list links owners to reward settings. Customer profile now explains current policy, historical awards, negative points-to-recover, current balance and owner adjustments. The shared **restaurant/bar and retail POS order** detail shows eligible estimated points before final payment and the actual award after settlement.
- Tests authored for opt-in defaults, form validity, partial/split payments, repeated payments, partial/full returns, disabled-policy reversals, existing-point corrections, ledger merge, currency mismatch and unlinked orders; prior shared-customer merge test adapted to its extended accounting evidence.
- Added `docs/LOYALTY_POINTS_POLICY.md` with math, staff workflow, limits, liabilities and documented deferred verification.
- **Phase 06 is still not complete:** coupon/redemption checkout economics, tier benefits, credit/voucher lifecycle, customer portal, accounting/financial liability policy, promotion precedence, accurate multi-terminal concurrency testing, PostgreSQL/RLS checks and browser certification remain outstanding. No source code was certified green here.

Reference design: Django transactional row locking and Yotpo's documented proportional handling of earned points on partial refunds (https://docs.djangoproject.com/en/5.2/topics/db/transactions/ ; https://support.yotpo.com/docs/point-balance-for-refunded-orders).

- Owners now see a small **Customer points programme** overview directly in the existing Customers & Guests directory: current rule, net issued points, sale awards, refund reversals, and manual corrections. The figures are labeled as points, never money or cashbook liabilities.


### 2026-10-16 — Phase 06: read-only points reconciliation primitive

- Added `apps.customers.loyalty_reconciliation` with tenant-scoped, read-only account and workspace point summaries separated into sale earnings, refund reversals, reward redemptions and manager adjustments.
- An individual account report exposes negative points to recover and flags refund reversals exceeding recorded sale awards; the workspace rollup counts negative accounts rather than masking them inside net points.
- The functions never rewrite historical records, turn points into cash value, or treat a legitimate post-refund negative balance as an automatic correction.
- This is a **backend foundation, not a completed reconciliation user journey**: owner/staff access, links, exports, anomaly resolution, transaction-level/source integrity checks, direct unit tests, database/tenant RLS evidence and browser verification are still required. Neither Phase 06 nor any other unfinished phase is marked complete.
- Code committed to `origin/main` as an implementation-first checkpoint; verification is intentionally not represented as performed.


### 2026-10-16 — Phase 06 reconciliation scale and regression contracts

- Updated the existing `apps.customers.loyalty_reconciliation` module so tenant negative-balance account counts are computed by grouped SQL rather than fetching each account into Python. Historical point entries remain untouched.
- Added focused `SimpleTestCase` contracts for no-entry defaults, negative balances after reversals, cross-tenant/merged-account rejection, source breakdown, and read-only grouped tenant summaries.
- Research basis: Django 5.2 aggregation documentation, https://docs.djangoproject.com/en/5.2/topics/db/aggregation/ . No external points-to-currency treatment or accounting liability was inferred.
- **Unverified implementation checkpoint**: tests were authored and committed, not executed. Staff-visible reconciliation, real database regressions, audit source tracing, API scopes and responsive browser certification remain pending; Phase 06 stays in progress.

### 2026-10-16 — customer points usability and import blocker

- Fixed the indentation error in `StaffCustomerListView.get_context_data` that prevented the customer staff view module from importing cleanly.
- Integrated the existing read-only loyalty reconciliation into the real **Customers & Guests** owner directory and **Customer profile** (earned points, refund reversals, manual corrections, recorded redemptions, actual balance, accounts requiring review). Updated the negative-balance message to show positive points-to-recover rather than a signed negative figure.
- Added database-backed tests covering two accounts with opposing balances, tenant isolation and merged-account exclusion. Existing unverified mocked reconciliation contracts remain separately authored.
- No checkout reward redemption or monetary benefit has been enabled, and nothing mutates historical financial transactions. Existing staff shell/nav, responsive card/table styles and per-customer permissions are reused.
- **Status**: work pushed to origin/main, not verified by a local Django runtime, PostgreSQL, browser or CI. Phase 06 is **still in progress**. No additional phase is marked complete by this checkpoint.


### 2026-10-16 — CI migration-drift repair for Phase 08/09

- Observed the actual GitHub Actions failure on main: Django system checks passed, while migration drift blocked the test suite before execution. Django requested `inventory.0009` for StockBatchAllocation.quantity validators and `purchasing.0010` for SupplierInvoice amount validators and recorded_by optionality.
- Committed both forward-only migrations with existing prior migration dependencies and fields matching current models. No historical stock, invoice, payment or supplier data is backfilled.
- GitHub Actions was newly queued at the time of this checkpoint. Passing CI, PostgreSQL/RLS, real browser and financial correctness are not claimed. Both phases remain in progress until their complete acceptance journeys and verification pass.
- This repair is prioritized ahead of more broad modifications so new changes do not hide a known broken release gate.

### 2026-10-16 — 9/34 milestone: actual CI triage

- Reviewed GitHub Actions run `38902175104` on main. Django migrations and system checks passed, but the automated suite ended with **456 passed, 25 failed and 5 skipped**; this is **not** a green release and **not** evidence for marking phases 05–09 complete.
- The traceback identified a deterministic crash in `apps.console.setup_flow.build_tenant_setup_state`: `has_services_line` and `has_events_line` were referenced before initialization. Reordered the business-line assignments before deriving `has_pos_work`, preserving existing setup and role rules.
- The change is committed to origin/main, and a follow-on CI run was in progress at the time of inspection. Existing dashboard/onboarding tests cover the affected path; no claim of a passing rerun is made.
- The other failing tests and all remaining customer, loyalty, inventory, batch and purchasing acceptance gaps still require fixes before any additional phase can be checked complete. Release certification must fail closed until all required external evidence exists.

### 2026-10-16 — CI triage: write-action visibility, hardware scope and scheduled report timezone

- Starting evidence: the last completed failed SQLite job reported **456 passed, 25 failed, 5 skipped** before the onboarding crash correction. System checks and migration consistency had passed. Later run outcomes must be checked independently; do not treat pending/cancelled workflow runs as passing.
- Updated shared staff sidebar so the **New order** POST shortcut is based on explicit operational write roles instead of broader orders read-navigation visibility. Reception and accountant read-only workflows no longer advertise a prohibited quick-create action. Existing role-workspace tests include a reception assertion for the exact form action.
- Device observation checks now load a fresh tenant configuration before authorizing kitchen hardware. This closes the stale-related-object path when the owner recently changed the business profile. The retail-only kitchen test remains the acceptance evidence to execute.
- Owner report date selection now loads current tenant timezone from the database, avoiding stale cached one-to-one settings. Existing daily/weekly/monthly, deduplicated mail and retry tests remain the acceptance evidence to execute.
- All changes committed to origin/main as implementation checkpoints. **Do not mark Phases 05–09 or any other phase complete without a green full suite and all feature-specific acceptance gates.** Physical hardware, PostgreSQL/RLS, browser/device workflows and provider certification remain unverified.

### 2026-10-16 — Codex continuation: green SQLite gate and Phase 06 owner consistency

- Reviewed Codex's actual new main commit `a3a7424843`: staff stock write-permission separation, receiving access, console/reception adjustments and expanded regressions. GitHub Actions run `38908841668` for that exact SHA **passed**: **483 passed, 5 skipped, 4 warnings** (plus 3 passing subtests), with Django checks and migration-drift gate successful. This is SQLite-only CI, **not** PostgreSQL/browser/provider or production certification.
- Corrected a real Phase 06 owner UI inconsistency: the per-source loyalty totals and net issued points now use active customer accounts only and the same reconciliation authority. Old merged-account ledger entries are not silently included in one total while omitted from another. No historical entries or financial transactions are modified.
- Added a database-backed regression for owner directory rendering where an archived merged account retains a legacy adjustment, ensuring the UI total and active-account reconciliation agree. Committed code and test to main; **these follow-on commits have not inherited the prior green test evidence** and require their own run.
- Phase 05–09 acceptance gaps remain. Do not mark additional phases complete solely from an overall green SQLite suite. Continue with end-user workflows, tenant permissions, PostgreSQL locking/RLS, responsive browser and provider evidence.

### 2026-10-16 — Phase 06 negative points recovery workflow

- Verified GitHub Actions run `38909467988` for main `7da92e40f57f`: **484 passed, 5 skipped, 4 warnings** and Django checks/migration-drift passed. This is SQLite evidence only.
- Extended the **existing** customer directory with an owner/admin-only `points_review=1` drilldown for customers with negative net ledger points; the filtered customer list preserves search and links to each existing account breakdown. Non-owner requests for the report return 404 to avoid tenant-wide loyalty disclosure.
- Existing owner summary links directly to this queue. Negative points remain an informational review signal, not an automatic charge, money balance or blocked refund. No ledger writes or changes to redemption policy.
- Added a database-backed test verifying filtered results and frontend role denial. New commits require their own CI run. Phase 06 remains **in progress** pending the documented remaining reward/checkout/coupon scope and external test gates.

### 2026-10-16 — Phase 20 permission-policy foundation

- Added a centralized, fail-closed inventory action capability map (view, adjust, transfer, count), extending the existing staff permission module rather than introducing another permission engine. Existing `membership_can_modify_inventory` delegates to the shared adjust capability, retaining current write-role behavior.
- Added tests covering storekeeper stock operations, accountant read-only access, front desk denial, inactive memberships and unknown capabilities. These tests must run in CI; authored tests are not passing-test evidence.
- **Phase 20 changes from pending to in progress, not complete.** Missing: consistent action maps and enforcement in POS/refund/void/reopen, lodging, finance, staff management, API parity, outlet restrictions and role presets. Follow existing module/scope checks; this helper is not authorization by itself.
- The previously green run on `7da92e40f57f` had 484 passed and 5 skipped. Later Phase 06 and Phase 20 commits must receive independent successful CI; no new overall completion count is asserted.

### 2026-10-16 — Phase 20 concrete staff action enforcement

- Verified GitHub Actions run `38921681863` for `963f9d65b78b`: **492 tests passed, 5 skipped** and Django checks/migration-drift passed. SQLite-only evidence; PostgreSQL/browser/release gates still outstanding.
- Integrated the newly centralized inventory capability policy into existing stock transfer and stock-count POST authorization. Transfer now checks the `transfer` capability; starting and completing a count now check `count`. Other stock write operations continue using the existing `adjust` compatibility helper. This is service-preserving permission parity, not an independent authorization engine; tenant/outlet/module scopes are still enforced by their existing views and services.
- Codex's end-to-end storekeeper stock transfer/count tests and the action-capability unit tests provide regression coverage to rerun. The new commit has not yet passed CI. Phase 20 remains in progress until other domain capabilities and API parity are delivered.

### 2026-10-16 — Phase 20 purchasing action permissions

- Verified GitHub Actions run `38923055890` for `615b20e66ddf`: **492 passed, 5 skipped**, system checks and migration consistency passed (SQLite only).
- Extended the existing shared staff permissions with distinct `purchasing.view`, `purchasing.receive`, `purchasing.manage` and `purchasing.supplier_payment` capability checks. The existing purchasing staff views now use `receive` for stock receipt and `manage` for changing POs and supplier operations, preserving current role behavior.
- Storekeepers can receive assigned stock without gaining supplier finance permissions. Unknown actions, missing or inactive memberships fail closed. Added standalone regression tests for these distinctions; existing end-to-end storekeeper receiving tests remain applicable.
- These are role checks only. Existing tenant/business module/outlet checks remain mandatory. The new commits require their own CI confirmation, and Phase 20 remains in progress pending other workflows, API parity, manager approvals and full certification.

### 2026-10-16 — Phase 17 EFRIS retry safety kickoff

- Reused the existing `apps.integrations` outbox and URA adapter rather than creating another fiscal flow. Official URA guidance identifies fiscal receipts/invoices and credit/debit notes with FDN, verification features and transaction requirements; the generic adapter is still an uncertified integration shell.
- Bounded automatic retries at three attempts, including scheduler and direct-processing paths. Unexpected provider exceptions now quarantine ambiguous outcomes without blindly retrying a document that may already have been accepted. Added two regression tests to cover unknown outcomes and exhausting retry limits.
- Updated `docs/COMPLIANCE_EFRIS_POSTURE.md` with explicit operator caution and certification gaps.
- Phase 17 advances from **pending** to **in progress** only. Fiscal-specific payload, receipt/credit-note lifecycle, status reconciliation, synchronous obligations, real sandbox credentials, end-to-end provider response evidence and user-facing correction workflow remain outstanding. These new changes need fresh CI confirmation; no production certification is claimed.

### 2026-10-16 — Phase 18 first management-facing report

- Reused `build_sales_summary` and `management_scope` in the existing Management → Reports screen. Added a date-bounded (maximum 31-day, past dates) owner/manager executive sales overview, showing actual payment/refund aggregates, net receipts, payment transaction count, top-selling items and accessible section totals with links to sales details. No separate revenue ledger or invented gross-profit number.
- Added a responsive server-rendered report section with useful zero-data and invalid-date states. Report uses management's role and outlet access restrictions.
- Added a regression test for manager access, invalid report windows, empty data and denial to non-manager. These new commits require fresh CI evidence.
- Phase 18 moves from **pending** to **in progress**. Still missing: occupancy/RevPAR, verified cost and margin, supplier balances/folios, arbitrary drill-down to register/employee/transaction, data currency separation, and complete browser/PostgreSQL certification. Do not mark this phase complete.
