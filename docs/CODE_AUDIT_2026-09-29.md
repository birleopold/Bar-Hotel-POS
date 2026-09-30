# Code audit checkpoint — 2026-09-29

Base commit: `2c76808` (`main`). This is a code and local SQLite test audit, not a production PostgreSQL, browser, hardware, or payment provider certification. The findings below refer to code on that commit and the fixes in the accompanying change.

## Files traced and fixes

| Path | Finding | Change |
| --- | --- | --- |
| `apps/pos/services/payments.py`, `apps/pos/models.py` | Tenant-wide idempotency keys could replay a payment or refund whose amount, method, reason, or restock instruction differed. Long keys were silently truncated. | Compare the immutable request fields before replay; reject oversized keys. |
| `apps/pos/services/payments.py`, `apps/inventory/models.py` | Whole-order refund restock used live item settings and duplicated quantities already returned; split tenders could never request final restock. | Derive direct-sale restock from recorded SALE movements, subtract earlier restocked line returns, and permit restock on the final split-tender refund. |
| `apps/lodging/services.py`, `apps/lodging/models.py` | A folio payment key reused against another folio returned the first folio's payment. | Validate the key and compare folio, amount, method, and reference on replay. |
| `apps/pos/services/offline.py`, `apps/pos/offline_views.py` | An applied offline mutation ID could replay even when the submitted operation changed. | Reject changed applied operations; preserve the existing failed-operation retry workflow for stale catalogs. |
| `apps/pos/services/orders.py` | Register closing included cash sales but omitted cash refunds made during the shift. | Subtract cash refunds and use one close timestamp for both query bounds and shift state. |
| `apps/pos/services/payments.py`, `apps/lodging/services.py` | A paid POS order attached to a guest folio created a new payable charge, including discounts in the wrong amount. | For new sales, post the discounted charge and matching paid-at-POS credit to the folio; validate open status and currency before closing payment. Finance income remains posted only once. |
| `apps/purchasing/services.py` | Purchase order status was checked on the caller's potentially stale object before locking the database row. | Validate status after taking the lock. |
| `apps/inventory/services.py`, `apps/inventory/serializers.py` | Count completion checked potentially stale session state; duplicate items could overwrite the count and produce misleading variances. | Lock the session before checking state; reject duplicate count items. |
| `apps/inventory/views.py`, `apps/inventory/serializers.py` | Stock list APIs and manual movement creation did not apply the membership's assigned outlet scope. | Apply existing membership outlet scope to reads and the write path. |
| `apps/api/report_views.py` | Sales summary and operations rollup showed totals for other branches within the tenant to a site-restricted member. | Scope payment and refund queries to assigned outlets. |

Regression coverage was added in `apps/finance/tests.py`, `tests/test_folio_settlement.py`, `tests/test_offline_v2.py`, and `tests/test_phase1_isolation_and_idempotency.py`. The local suite passed 242 tests after the code changes, and the additional post-refund line-return guard passed separately. Django system and migration checks passed. Production PostgreSQL and browser checks remain separate release gates.

## Earlier open findings (tracked through the next implementation)

1. **Historical folios and charge-to-room:** New paid POS sales now have matching folio charge and paid-at-POS credit. Previously posted positive-only POS folio lines remain as recorded. Review and reconcile these against actual guest payments before any historical backfill. A separate charge-to-room flow (unpaid at POS, settled at checkout) still requires a defined accounting and stock-consumption policy.
2. **Recipe ingredient refunds:** Whole-order restock now follows the original direct-sale movements and deducts prior retail line returns, including on the last split-tender refund. It intentionally does not put consumed recipe ingredients back into stock; whether prepared goods can be recovered needs an explicit operational policy.
3. **Return workflow linkage:** Retail line returns and monetary refunds remain separate actions. The restock correction prevents duplicate direct-sale stock increases, but a complete customer return should eventually link quantity, tender refund, and approval in one workflow.
4. **Purchase cashbook semantics:** `post_purchase_receive_expense_from_movement()` records purchase receipt cost as a cashbook expense on receipt, although supplier payment may occur later. The cashbook currently mixes accrual-like goods receipt with cash movements; commercial reconciliation needs payable and payment states or a clearer label.
5. **PostgreSQL concurrency and UI:** The local SQLite suite does not prove lock behavior under simultaneous checkout, receiving, stock counts, and register close. Browser coverage for mobile POS, KDS, hotel folios, and offline replay remains a separate release gate.

These open items should not be represented as completed features or certified controls.

## Follow-up implementation on current `main`

The follow-up change treats settlement as an explicit action in each workspace. The staff UI and API now both expose supplier payments and charge-to-room, and the new endpoints are included in `docs/openapi.yaml`.

Local verification: Django system and migration checks passed; the full SQLite-backed suite passed **252 tests**. This does not certify production PostgreSQL locking, RLS role behavior, visual layout, or external hardware.

| Area | Implemented behavior | Scope and limits |
| --- | --- | --- |
| Purchasing and cashbook | Goods receipt updates stock and a delivery record. A separately recorded supplier payment creates the cashbook expense. Received value, paid amount, and unpaid received value appear on the PO screen. Payment retries compare immutable fields and cannot exceed the value of costed goods received. | Existing receipt expenses remain untouched. POs with legacy receipt postings block new supplier payments until a human reconciles them. Missing unit costs can be confirmed once, with an audit event, before settlement. The app does not model supplier invoices, credit notes, deposits, or currency conversion. |
| Hotel and POS | Staff can charge an open order's unpaid balance to an open same-site, same-currency folio. Any partial POS tender becomes a folio credit; stock is consumed once, the order closes, and the remaining balance is collected through folio payment. Direct order PATCH closure is rejected. | A charged-to-room order remains `is_paid=False` because POS tender has not paid it; the folio holds the receivable. Historical folios are not rewritten. |
| Returns | Physical line restock checks recorded `SALE` movements instead of current product settings, and cannot add more than the sale consumed. The retail UI explains that physical return and customer refund are separate actions and shows return history. | Monetary refund and physical return are still separate audited operations; staff must match them. Recipe ingredient `RECIPE` movements are deliberately not reversed. |
| Tenant scope | Order and table API reads are limited to the membership's outlets. | Production PostgreSQL RLS behavior still needs an integration run. |

### Historical reconciliation (read-only)

Run on the direct VPS with its normal Django environment:

```bash
cd /path/to/Bar-Hotel-POS/backend
python manage.py audit_legacy_postings --tenant-id TENANT_UUID
```

The JSON report lists paid POS orders with positive-only folio lines and legacy purchase receipt movement IDs. Match each item against actual guest and supplier payments before adjusting historical books. The command changes no data.

### Release evidence still required

1. Apply migrations and run the full backend suite against a disposable PostgreSQL database with the same tenant RLS role setup as production. Exercise concurrent checkout, PO receiving, stock counts, supplier payments, and shift close. SQLite cannot certify row locks.
2. Use a real browser at desktop, tablet, and phone widths for cashier, retail return/refund, room charge, folio settlement, purchasing receipt/payment, KDS, and offline replay. Check keyboard focus, scrolling, and touch targets. Template loading and HTTP tests do not certify visual layout.
3. Validate receipt printer, scanner, payment provider, and physical devices at their deployment sites. No hardware or external payment certification is implied by the local suite.
4. Review recipe ingredient recovery and the business policy for linking a return quantity to a specific tender refund. Automating either without that policy could create stock or cash discrepancies.

## 2026-09-30 implementation: linked retail returns

The retail and supermarket order screen now offers a manager-approved **Return and refund** action. It records the returned line and quantity, the actual customer refund against the selected original payment, and optional direct-sale stock receipt in one database transaction. A nullable one-to-one link on `SupermarketLineReturn.refund` preserves older physical-only return records. The same action is available at `POST /api/v1/orders/{id}/retail-line-refunds/` with `Idempotency-Key`; retries compare both the monetary refund and return details. A failed quantity or stock check rolls back the refund and its finance posting. The return history displays the linked amount and tender. Physical-only exchanges and price-adjustment refunds remain available and are labeled separately.

| Files | Audit finding and treatment |
| --- | --- |
| `apps/pos/services/returns.py`, `services/payments.py`, `services/orders.py` | The previous independent actions could leave money and returned stock unmatched. The new transaction reuses the established tender caps, stock movement checks, and audit events, then links the successful records. |
| `apps/pos/models.py`, `migrations/0010_supermarketlinereturn_refund.py` | A return had no reference to a refund. The optional protected link supports existing rows without rewriting historical data. |
| `apps/pos/views.py`, `serializers.py`, `docs/openapi.yaml` | The HTTP workflow checks outlet scope, manager approval, idempotency, line ownership, quantity, amount, and tender. |
| `apps/staff/views_ops.py`, `forms/pos_orders.py`, `templates/staff/order_detail*.html` | Staff can enter the actual refund amount for discounted/taxed sales and see the returned item and tender together. The physical-only and adjustment workflows have explicit labels. |
| `apps/finance/tests.py`, `apps/staff/tests.py` | Service, HTTP permission and replay, posting rollback, and rendered staff action have regression coverage. |

The amount is entered by an approving manager because the order can contain discounts, tax, and split payments. There is no automatic per-unit allocation or enforced equivalence between item value and tender amount. Recipe ingredient recovery, historical pairing of older independent records, production PostgreSQL concurrency, and real device/browser checks remain release work.

### PostgreSQL race check prepared

`backend/tests/test_postgres_settlement_concurrency.py` starts two independent database connections that each try to pay the full received value of the same purchase order. On PostgreSQL, exactly one payment and one cashbook expense should survive. The test skips SQLite because it cannot verify PostgreSQL row locks. Run it on the disposable PostgreSQL test database with `pytest -q tests/test_postgres_settlement_concurrency.py`; the local SQLite pass below does **not** execute that assertion. Additional concurrent checkout, receiving, stock count, and shift-close runs still need PostgreSQL release evidence.

## 2026-09-30 shared terminal authentication

Staff can enroll a workspace PIN only after entering their own account password. A visible **Lock terminal** action logs out the current worker and leaves a signed, 12-hour tenant/section marker for the next worker. The next worker selects their identity and enters a PIN; a fresh session uses their own membership, outlet limits, and audit attribution. Server and browser idle limits lock PIN-enabled sessions after two minutes. Five failed guesses lock a PIN for 15 minutes. PIN sessions cannot access console or API routes; full password login remains available. The anonymous PIN screen sets the tenant context from the signed marker so PostgreSQL RLS can scope membership reads. See `docs/STAFF_SHARED_TERMINAL.md` for the operator flow and deployment checks.

Follow-up: credential changes now invalidate older PIN sessions at their next staff request inside the RLS-scoped middleware path. The terminal list applies the existing role-specific outlet rule, and completed orders show a direct **Done · lock terminal** action after receipt access. Regression tests cover both credential revocation and role-based section filtering.

## 2026-09-30 team and register workflow

The team directory now exposes PIN readiness, name search, explicit row selection for bulk actions, and an owner/admin-only PIN revoke action. Revocation is tenant-scoped and audited; the worker must use their own password to enroll again. The register screen now previews opening float, cash sales, cash refunds, and expected cash, and recent shifts show expected, counted, and variance. The close command and preview share one cash calculation. Opening a shift locks the outlet row before checking for another open shift; a PostgreSQL-only concurrency regression was added but has not yet been exercised locally. See `docs/STAFF_SHARED_TERMINAL.md` and `docs/POS_REGISTER.md`. The local test suite still does not certify physical cash handling, browser layout, or PostgreSQL locking.

## 2026-09-30 staff interface pass

The dashboard puts role-specific work before administration, names the signed-in worker when available, and uses consistent icons and quieter task cards. Its empty workspace prompt now uses a local illustration made from CSS instead of an external stock image. The orders screen presents the section in scope, direct order and tab actions, semantic counts, and a useful empty state when no checks are active. The navigation makes terminal locking a larger, more prominent action on mobile and desktop. A rendered template regression checks the task order and empty lanes. These changes need visual review at real browser widths and with tenant theme colors before layout can be considered certified.

Follow-up: the floor screen now distinguishes editable table setup from read-only cards, shows an explicit empty state, and links workers back to Orders for guest checks. Invalid register amounts now retain the entered note and display field errors on the same page. Browser inspection of the local server was attempted but the available cloud browser blocked loopback URLs; no visual browser certification is claimed for this follow-up.

The next cashier pass keeps live service lanes independent from history status/search filters and limits the orders list and lane fragment to the member's accessible outlets, including in All sections mode. The summary calls non-open checks “Recent activity” because it includes cancellations. On compact screens, Lock terminal sits beside the workspace name before navigation, and navigation/section controls meet the shared touch-target minimum. Query and rendered-header regressions cover these changes; a reachable browser environment is still required for visual inspection.

## 2026-09-30 full-suite execution plan and workstation checkpoint

`docs/SUITE_IMPLEMENTATION_TODO.md` is the required full-suite checklist and records all proposed improvements except the explicitly avoided architecture/features. This checkpoint adds a tenant/outlet-scoped Workstation model, owner/admin device configuration, authorized staff browser selection, hardware labels, last contact and optional shift linkage. Signed device selection is a preference, not an authentication credential. An open shift prevents moving/disabling its device. Existing financial records are not rewritten, and one open shift per section remains enforced until payments/refunds can be attributed per till.

Full SQLite verification: **278 passed, 2 PostgreSQL-only skips**. Django check and migration consistency passed. Seven device regressions cover cross-tenant/outlet restrictions, management permissions, duplicate code validation, signed selection/handoff, shift association and open-shift edit protection. PostgreSQL RLS/concurrency, real browser layout and hardware certification remain outstanding. New migrations 0011/0012 are additive and preserve legacy nullable links; apply, reverse to 0010 and reapply passed on a disposable SQLite database. Full phase 01 and the broader suite are not complete.
