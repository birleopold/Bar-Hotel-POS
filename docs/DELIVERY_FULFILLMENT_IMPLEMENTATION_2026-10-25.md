# Shared delivery fulfillment — POS integration contract

**Date:** 25 October 2026  
**Decision:** Build an optional **Delivery / Fulfillment** capability *inside* the existing multi-tenant POS. Do not create a second order ledger or a courier-only SaaS for ordinary business deliveries.  
**Implementation state (25 October D01/D02 continuation):** D01 migration-backed `OutletDeliverySettings` and `OrderDelivery` records with PostgreSQL RLS, outlet-manager opt-in, paid-order registration, duplicate pickup/delivery prevention and manager-scoped delivery staff queue are now source-implemented. D02 additionally has guarded worker assignment and fulfillment transitions. The migration and test suite must pass, and deployment must be verified, before enabling in production. COD, rider payments, delivery fees, KDS/hotel acceptance and third-party integrations are **not implemented**.

## Evidence and external workflow comparison

- Shopify POS (September 28, 2026): local delivery can be selected on a checkout sale, with address, contact, delivery fee, receipt/customer screen, preparation and fulfillment. Official: https://changelog.shopify.com/posts/local-delivery-orders-in-shopify-pos and https://help.shopify.com/en/manual/sell-in-person/shopify-pos/order-management/local-delivery-orders
- Shopify local delivery fulfillment: unfulfilled → ready → delivered, with pick/pack, delivery instructions, and delivered confirmation. Official: https://help.shopify.com/en/manual/fulfillment/fulfilling-orders/local-delivery-fulfillment
- Toast Orders Hub: one off-premise order console supports delivery, takeout, in-house drivers and dispatch, separate from kitchen production. Official: https://support.toasttab.com/en/article/Managing-Off-Premise-Orders-with-Orders-Hub

These are design references, *not* dependencies. No paid third-party provider or courier marketplace is required.

## Product boundaries

| Business line | First-party delivery | Existing separate processing |
|---|---|---|
| Supermarket/grocery/retail | Pick, pack, dispatch purchased items to a destination | Cashier and stock service already own sale, retail pickup stays separate |
| Restaurant/cafeteria | Approve, prepare through existing KDS, rider handoff, deliver | Kitchen statuses never become delivery statuses |
| Bar/lounge | Pack approved product order and dispatch when enabled and lawful | Respect regulated-goods age/local-delivery restrictions and time windows |
| Hotel/lodging | Guest-room service to valid current room/folio, or external local delivery where outlet supports it | Do not equate hotel guest rooms with customer street addresses or change folio/accounting rules |
| Other modules | Off unless explicitly configured and supported | No automatic inheritance of all POS features |

**Not included in the first release:** third-party rider marketplace, maps/route optimization, live GPS driver tracking, external food-delivery aggregator, automatic merchant payout, new end-consumer mobile application, wholesale vehicle fleet management. Those can be integrations later.

## Canonical records and invariants

1. **Order remains the single sale of record.** A delivery links to one existing `Order`, tenant and fulfilling outlet; it never creates a second sale, doubles stock movement, or bypasses the current paid/folio ledger.
2. **Delivery is a distinct fulfillment record.** New migration required: `OrderDelivery` (one-to-one with order for initial rollout) with tenant, outlet, destination type, recipient name/contact, address or verified guest room/folio, address instructions, promised time, fee + currency snapshot, status, assigned driver, dispatch/delivery timestamps, delivered-by, safe proof note, failure/return reason, created/updated actor. Keep contact/address access limited by role; do not put PII in audit payload or publicly guessable URLs.
3. **Independent state dimensions:** `Order.status/is_paid` reflects sale/finance; `OrderDelivery.status` reflects preparation and delivery. A paid order may be unfulfilled. A COD delivery may be out for delivery but unpaid. No delivery state transition changes payment or stock by itself.
4. **Lifecycle:** requested → accepted → preparing → ready → dispatched → delivered. Staff may cancel before dispatch or mark dispatch failed, retry from ready, or return. Terminal delivered/cancelled/returned states are immutable except a privileged audited correction with reason. Use row locks and idempotency keys for transition/retry.
5. **Payment policy:** Phase 1 supports **fully paid sale before dispatch** only (card/cash/mobile money using the existing POS payments). Phase 2 adds manager-authorized COD and partial prepayment with driver collection reconciliation, shift allocation, receipts and no fake paid status. Cash collected by riders is not revenue until recorded through a verified cash/settlement route.
6. **Delivery charge:** must be approved and calculated **inside the existing order totals before final payment**, with tax policy and currency snapshot. Do not add an arbitrary fee to an already paid historic order or create a new movement on dispatch. Manual zero fee allowed. Do not mix a rider's tip, merchant delivery revenue and third-party courier payable.
7. **Stock:** use present `validate_and_consume_stock_for_paid_order` exactly once upon full settlement for phase 1. Delivery preparation reserves the ordered goods operationally, but any future *stock reservation* needs its own allocation mechanism and concurrent check (do not represent reserved stock as sold twice). For COD extend with safe inventory reservation/decrement policy before dispatch.
8. **Auth/multitenancy:** every query scoped to active tenant and membership-authorized outlet, with server-side action permissions for create/prepare/dispatch/deliver/cancel; driver can access only assigned manifest and confirm delivery. One tenant's deliveries never appear in another tenant. Fizo is a test tenant, never global branding.
9. **Completeness:** staff-facing Delivery queue, detail screen and badges, optional checkout method, printable packing/delivery slip, staff notifications, SMS/mobile money hooks where configured, address and time validation, failed/returned workflows and reporting. Multi-screen cashier, kitchen and guest flows must remain visually consistent with their lines.
10. **Isolation:** enabling delivery in one line or outlet never adds room numbers/table numbers/customer-account requirements to supermarket walk-in checkout. Pickup and delivery cannot both be active fulfillment for one physical order unless explicitly split at line level in a later release.

## Phased implementation

| Package | Work | Prerequisite / acceptance |
|---|---|---|
| D00 (committed groundwork) | `apps.pos.services.delivery_policy` validates destination, stage transitions and fee; matching SimpleTestCase contract | Unit suite + quality CI must run; this is **not a usable delivery feature** |
| D01 | Migrations, `OrderDelivery` one-to-one + tenant/outlet constraints and indexes; per-outlet enablement | `makemigrations --check`, SQLite/PostgreSQL migration, tenant/role tests |
| D02 | Fully paid retail deliveries: save address/recipient, choose delivery at checkout, pack/dispatch/confirm, reprint, keep stock singly posted | Two customers, payment/replay/refund, delivery failure, hardware receipts |
| D03 | Restaurant food delivery with existing KDS; driver assignment after kitchen ready; no shared-table lifecycle | KDS/fulfillment independent status tests |
| D04 | Hotel guest-room service linked to real occupied room/folio, staff handoff; external delivery optional | Folio and room scope, no duplicate guest charge |
| D05 | Bar delivery via explicit business enablement, legal controls, customer handover checks | Local policy signoff |
| D06 | COD/partial-pay rider collection, returns/refunds and driver shifts, delivery fees, SMS, business reports | End-to-end financial reconciliation, duplicate submission tests |
| D07 | Optional integrations: online ordering, third-party dispatch, mobile driver UI, maps/route estimates | Contracts, API idempotency, consent/privacy and provider sandbox |

## D01/D02 source progress (25 October 2026)

- `backend/apps/pos/models.py`: `OutletDeliverySettings` (default off, one-to-one per outlet) and `OrderDelivery` (one-to-one existing sale, separate status, destination/contact snapshot, driver, optional scheduled time, fee/currency snapshot, handoff timestamps). `0030_delivery_fulfillment.py` creates the tables; `0031_delivery_fulfillment_rls.py` adds PostgreSQL tenant RLS to both. No conversion or deletion of historical POS orders.
- `backend/apps/pos/services/deliveries.py`: manager-only enable/disable, paid-order delivery registration with recorded-payment check and tenant/outlet scoping, safe replay on identical request, customer pickup mutual exclusion, and role/outlet-scoped driver assignment and audited state changes. No new payment or stock mutation.
- `backend/apps/pos/services/pickups.py`: reject paid pickup if that sale already has a delivery record. Pickups remain independent where not delivery-assigned.
- `backend/apps/staff/views_delivery.py` and `staff/pos/deliveries.html`: manager-only Delivery queue at `/staff/pos/deliveries/` with opt-in per outlet, eligible settled-sale selector, recipient/destination form, worker assignment and state actions. Existing staff navigation links to it. Workers are scoped to accessible outlets.
- Hotel-room deliveries in the service require a matching actual checked-in folio/reservation room; external deliveries require recipient name/contact/address. Cash-on-delivery and unpaid orders are rejected in the first release.
- `backend/tests/test_delivery_persistence.py` covers disabled-by-default, settled-ledger requirement, duplicate pickup prevention, replay, tenant/manager authorization, state transitions, hotel checkout, and rendered staff queue/registration; `test_postgres_rls_policy_presence.py` checks both delivery tables. Existing `quality.yml` runs persistence and policy tests in PostgreSQL.
- **Not yet accepted:** observed `makemigrations --check`/PostgreSQL CI results, actual migration execution, browser flows, all five target viewport screenshots, driver confirmation on physical devices, restaurant KDS, hotel room/folio financial integration, fee calculation and cash-on-delivery reconciliation. Do not represent these as tested or shipped.

## Current implementation artifacts

- `backend/apps/pos/services/delivery_policy.py` — destination/fee/status contract, no persistence
- `backend/tests/test_delivery_policy.py` — cross-line policy regression
- `.github/workflows/quality.yml` — add policy tests to existing suite
- Existing `apps.pos.services.pickups` remains unchanged and distinct.

## Acceptance evidence gates

- Never show a delivery button to customers until D01–D02 migrations, UI, business configuration and permission test pass.
- Verify KDS, hotel folio, outlet permissions and payment/stock isolation together, not one controller at a time.
- Compare approved UI at 1536×1024, 1366×768, 1024×768, 390×844 and 1920×1080; keyboard and touch; no extra CSS foundation.
- Run PostgreSQL CI, genuine browser workflow and real payment/stock rollback scenarios before marking D02 or later complete.
