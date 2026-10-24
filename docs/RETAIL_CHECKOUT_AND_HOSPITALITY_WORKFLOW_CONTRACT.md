# POS workflow contract — 24 October 2026

Status: **Approved behavioral target / acceptance specification**, not a claim of production certification.
Scope: all tenants. Fizo is a **test tenant**, never a product, CSS ownership, or tenant naming convention.
Source: owner feedback and reported production symptoms during October 2026 implementation.

## Product boundaries

- **Supermarket, grocery and general retail** use a dedicated cashier checkout with an optional second screen facing **one current shopper only**. No tables or mandatory customer record; register normally belongs to one cashier, without constant forced PIN relocking.
- **Bar, restaurant and hotel** use their own appropriate order, table, room/folio and service workflows. Their kitchen/bar/department displays show **multiple assigned orders** with states pending, accepted, preparing, ready, served. A ready item remains visible until served. Never reuse the retail second-screen semantics for a preparation queue.
- White-label settings (business name, logo, currency, business modules, access and products) are resolved from **the authenticated tenant**, not Fizo or hardcoded USD.
- Maintain shared core CSS with only necessary industry-specific styling; legacy `fizo-` filenames/classes do not confer tenant identity. Never rename them without coordinated references, tests and verification.
- Use owner-approved UI images in `docs/design/references/` as layout targets, but functionality and data correctness take priority during this stage.

## Retail: current basket vs parked basket

1. Scanning/selecting a product updates the active cashier basket (quantity, unit price, line value, total); ordinary items increment in **whole units**, measured products may permit fractional values as configured.
2. The paired client monitor shows **only that cashier/register's active shopper**: items, quantity, unit amount, line amount, total, recorded payment, balance. It updates without pressing “send to customer.” Do not rotate through old orders or expose customer personal details or controls.
3. The cashier can enter cash **tendered**, which may exceed the outstanding amount; calculate change as tender minus amount collected, **not** additional revenue. Cash below the balance can be recorded as a genuine partial payment, leaving an outstanding amount.
4. Multiple partial payments on the **same sale** may use cash, mobile money and card, each recorded separately with idempotency and no excess collection. Displayed mobile-money method selection does **not** by itself verify an external provider transfer.
5. **Hold Sale** parks an unpaid or partially paid basket, preserving products, quantities, payment history and balance. Label is optional at a retail till: derive a reference if blank. Holding must **leave** the active checkout and blank its paired client screen; cashier proceeds to the next shopper immediately. It must not cancel, settle or delete the old sale.
6. Retrieve a held basket via Held sales; continue adding products/recording remaining payments. Explicitly resumed basket becomes active. Upon reaching full payment, mark sale paid/closed, retain original payment method records and issue accurate final receipt; no further collection.
7. When no basket is being served, the client monitor displays a **neutral welcome/idle screen**. Paid, cancelled and held orders must never resurface spontaneously. **No alternating between receipt references.**
8. Client display is scoped to the actual register/session; same cashier at another register or old browser windows must not hijack it. Current in-repo active key is tenant/outlet/cashier; **workstation-level isolation and end-to-end double-monitor validation remain open**.
9. Client-side tender preview uses same-origin browser storage; **it is not yet cross-device synchronization or a recorded financial transaction**. On refresh, basket/payment data must be server-authoritative. Do not claim a verified remote customer terminal.
10. Currency: new orders use each tenant's configured currency. For an existing sale, do not convert amounts by changing a label. Only empty unpaid unaccounted legacy baskets may be safely relabelled. Completed/payment-bearing history remains immutable. Products and receipts must match the active sale currency; future UI should clarify any mismatch rather than pretend conversion.

### Cashier acceptance examples (UGX)

| Basket | Tender / payments | Expected result |
|---|---|---|
| 35,000 | Cash handed over 50,000 | Record 35,000 payment; show 15,000 change; close sale |
| 35,000 | Cash paid 15,000 | Record 15,000; show 20,000 due; may hold |
| 35,000 | 15,000 cash + 20,000 mobile money | Two distinct records; due zero; close |
| 35,000 | 10,000 cash + 15,000 mobile money + 10,000 card | Three distinct records; close |
| 35,000 | 15,000 paid, hold and resume | Same basket/reference and 20,000 due, not a new sale |
| 35,000 | Hold before completion | Client screen clears; new shopper sees only their own basket |

## Hospitality acceptance

- Kitchen, bar and service lines separated by configured station and user's authorized outlet/role; independent of retail shopper displays.
- Pending → accepted/preparation → ready → served advances with authorized events, not guessed from payment status.
- Ready items persist until acknowledged served; paid orders can still have prep work where applicable.
- Real-time screen refresh, permissions, routing, and ticket lifecycle verified separately per kitchen/bar/hotel service role.

## Implementation checkpoints vs verification

Existing code paths at time of writing:
- `backend/apps/staff/views_ops.py`: cashiers, new baskets, hold, payment and UI context.
- `backend/apps/pos/services/payments.py`: partial/mixed tender recording, payment idempotency, final settlement.
- `backend/apps/staff/views_customer_display.py` and `templates/staff/pos/customer_display*.html`: paired retail display.
- `backend/apps/staff/static/staff/customer-display-live.js`: 1.5-second DOM refresh; currently browser-storage preview of cash tender.
- `backend/apps/staff/views_kds.py`, `backend/apps/pos/services/kds.py`: hospitality preparation status and station scope.
- `backend/apps/pos/management/commands/reconcile_open_order_currency.py`: safe currency repair requires production PostgreSQL config.
- Deployment uses `deployment/contabo/deploy-app.sh`, `origin/main`, no feature branches.

**Outstanding / cannot mark complete merely from commits:**
- Cross-register/customer-monitor isolation, avoiding old receipt oscillation; explicitly exercise hold, resume, pay, next customer under concurrent cashiers.
- Actual production full-flow tests of over-tender, under-tender, mixed card/mobile money/cash, hold/resume, final receipt, and rollback/retry.
- Guarantee the on-screen cash tender and change remain accurate across browser profiles/devices and after sale switching; consider server-backed per-register ephemeral tender state.
- Verify server-authoritative current basket, including explicit resume of a held basket and no old basket resurrection.
- Tenant-specific currency throughout catalogue, basket, receipt, reports; no implicit foreign-exchange conversion.
- End-to-end hospitality state transitions and separation across kitchen/bar/hotel stations.
- Pixel-close visual acceptance against approved screenshots on desktops, tablets and mobiles.
- Review CI results and fix genuine failures; production deployment success does not equal feature acceptance.

## Development discipline

Implement complete functional slices across model/service/API/views/template/navigation/permissions/tests. Keep multiple tenants isolated, preserve payment/audit history, avoid repeating fixes or merely changing tests to hide regressions. Commit directly to `origin/main` as directed. Record verified evidence before marking an item complete.
