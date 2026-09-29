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

## Open findings requiring a separately certified change

1. **Historical folios and charge-to-room:** New paid POS sales now have matching folio charge and paid-at-POS credit. Previously posted positive-only POS folio lines remain as recorded. Review and reconcile these against actual guest payments before any historical backfill. A separate charge-to-room flow (unpaid at POS, settled at checkout) still requires a defined accounting and stock-consumption policy.
2. **Recipe ingredient refunds:** Whole-order restock now follows the original direct-sale movements and deducts prior retail line returns, including on the last split-tender refund. It intentionally does not put consumed recipe ingredients back into stock; whether prepared goods can be recovered needs an explicit operational policy.
3. **Return workflow linkage:** Retail line returns and monetary refunds remain separate actions. The restock correction prevents duplicate direct-sale stock increases, but a complete customer return should eventually link quantity, tender refund, and approval in one workflow.
4. **Purchase cashbook semantics:** `post_purchase_receive_expense_from_movement()` records purchase receipt cost as a cashbook expense on receipt, although supplier payment may occur later. The cashbook currently mixes accrual-like goods receipt with cash movements; commercial reconciliation needs payable and payment states or a clearer label.
5. **PostgreSQL concurrency and UI:** The local SQLite suite does not prove lock behavior under simultaneous checkout, receiving, stock counts, and register close. Browser coverage for mobile POS, KDS, hotel folios, and offline replay remains a separate release gate.

These open items should not be represented as completed features or certified controls.
