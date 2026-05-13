# Staff UI vs API parity

**Purpose:** Single checklist for integrators and maintainers: what exists on **`/api/v1/`** (JWT + `X-Tenant-Id`) versus **`/staff/`** (session + tenant in session). Update this file when you add or retire a flow.

**Convention**

| Column | Meaning |
|--------|---------|
| **API** | REST endpoints under `/api/v1/…` (see `apps/api/urls.py`). |
| **Staff** | Server-rendered views under `/staff/…` (see `apps/staff/urls.py`). |
| **Parity** | **Full** ≈ same business actions available in both channels where applicable; **Partial** ≈ read-only or subset; **None** ≈ only one channel. |

---

## Operations & POS

| Domain | API | Staff | Parity | Notes |
|--------|-----|-------|--------|-------|
| Orders (CRUD, lines, pay, refund, void, discount, promotion) | `orders` viewset + actions | `/staff/orders/`, order detail, print | **Full** | API is system of record; staff is primary floor UI. |
| Tables | `tables` | `/staff/tables/` | **Full** | |
| KDS / prep queue | `GET kds/tickets/`, `POST …/kds-line/` | `/staff/kitchen/` + WebSocket refresh | **Full** | Realtime: Channels `ws/kds/<tenant>/<outlet>/`. |
| POS shifts | — | `/staff/pos/shifts/` | **Partial** | Staff-only; no dedicated shift API in router. |
| Offline sync | `GET pos/catalog-version/?outlet=` + `POST pos/offline-sync/` + **`POST pos/offline-sync/batch/`** (≤50 ops) | **`/staff/pos/offline-queue/`** (read-only log) | **Partial** | Replay on API; staff is monitoring. **409 `catalog_stale`** persists a **failed** queue row; staff table compares **`payload.catalog_version`** to the live server pin. Batch **`depends_on`**; lines may include **`modifier_option_ids`**. |
| Sales summary | `GET reports/sales-summary/` | `/staff/reports/sales/` (`?format=csv` export) | **Full** | Staff CSV includes section / method / outlet / top items rollups. |
| Ops rollup (daily series) | `GET reports/operations-rollup/` | — | **API-only** | **`by_day`** for dashboards. Celery **`daily_operations_digest`** (06:00 UTC beat) builds **sales + cashbook CSV** using the same queries as staff exports; logs by default; set **`DAILY_OPERATIONS_DIGEST_SEND=true`** to email owners/tenant admins. |
| Payment webhooks | `POST integrations/payment-webhook/` (secret + **X-Tenant-Id**) | — | **API-only** | Set **`PAYMENT_WEBHOOK_SHARED_SECRET`**; idempotent **`event_id`**. |

## Catalog & pricing

| Domain | API | Staff | Parity | Notes |
|--------|-----|-------|--------|-------|
| Menu categories | `menu/categories` | via console + staff menu list | **Partial** | Staff **`/staff/menu/`** is operational view; authoring leans console. |
| Menu items | `menu/items` | same | **Partial** | |
| Promotions | `menu/promotions` | `/staff/promotions/` | **Full** | |
| Modifiers (options on items) | **`menu/modifier-groups/`**, **`menu/modifier-options/?group=`**; items expose **`modifier_groups`** + **`modifier_group_ids`**; order lines support **`modifier_option_ids`** | Console **`/console/org/menu/modifier-groups/`** (groups + options); menu item form attaches groups; **`/staff/orders/<id>/`** add-line checkboxes | **Partial** | Staff catalog authoring remains console-first; floor POS applies modifiers on add line. |
| Recipes / BOM | `menu/items/<id>/recipe/` (per item) | console | **Partial** | Staff floor rarely edits BOM. |

## Inventory & purchasing

| Domain | API | Staff | Parity | Notes |
|--------|-----|-------|--------|-------|
| Stock balances | `stock/balances` | `/staff/inventory/` | **Full** | |
| Movements / receive / adjust | `stock/movements` | movements + CSV upload templates | **Full** | |
| Transfers | `stock/transfers` | `/staff/inventory/transfer/` | **Full** | |
| Stock counts | `stock/count-sessions` | `/staff/inventory/counts/` | **Full** | |
| Suppliers | `purchasing/suppliers` | `/staff/purchasing/suppliers/` | **Full** | |
| Purchase orders | `purchasing/purchase-orders` | `/staff/purchasing/purchase-orders/` | **Full** | |

## Finance

| Domain | API | Staff | Parity | Notes |
|--------|-----|-------|--------|-------|
| Categories / cashbook | `finance/categories`, `finance/entries` | `/staff/finance/` (`?format=csv`), create entry + category | **Partial** | Staff CSV export for filtered cashbook; API CRUD for integrators. |

## Lodging

| Domain | API | Staff | Parity | Notes |
|--------|-----|-------|--------|-------|
| Room types / rooms | `lodging/room-types`, `rooms` | `/staff/lodging/room-types/`, `rooms/` | **Full** | |
| Rate windows | `lodging/rate-windows` | console-heavy | **Partial** | Staff lists exist; deep yield UI TBD (roadmap §4). |
| Reservations | `lodging/reservations` + `post-folio-charge` | `/staff/lodging/reservations/` + **`/staff/lodging/tape-chart/`** | **Full** | Room-night folio lines post **on check-in** when rate windows exist (`night_charges`). Tape chart = lightweight occupancy grid. |
| Folios | `lodging/folios` | `/staff/lodging/folios/` | **Full** | |

## Events

| Domain | API | Staff | Parity | Notes |
|--------|-----|-------|--------|-------|
| Spaces | `events/spaces` | `/staff/events/spaces/` | **Full** | |
| Bookings | `events/bookings` (overlap validation on create/patch) | `/staff/events/bookings/` + **`/staff/events/calendar/`** (week) | **Full** | **`deposit_amount`** on model; list shows deposit; settlement to orders/folios still integration-phase. |

## Platform & governance

| Domain | API | Staff | Parity | Notes |
|--------|-----|-------|--------|-------|
| Health | `GET health/` | — | **API-only** | |
| Auth (JWT, signup, password) | `auth/*`, `me/` | `/staff/login/` | **Partial** | Different auth mode by design. |
| Tenant settings (read/update) | `tenant/settings/` | workspace settings templates | **Partial** | |
| Invites | `invites/`, `invites/accept/` | workspace members | **Partial** | Accept often API/browser link. |
| Integration registry | `integrations/links` | `/staff/settings/integrations/` + **`/staff/settings/integrations/efris/`** (URA adapter + queue) | **Partial** | EFRIS is optional; queue visible on staff page. |
| **EFRIS outbox** | — (processing via Celery) | `/staff/settings/integrations/efris/` | **Staff-first** | Toggle + credentials + submission status; admin **`EfrisSubmission`** for platform ops. |
| Audit events | `audit-events` | `/staff/settings/audit/` (`staff-workspace-audit`) | **Partial** | Staff is read/filter UI; writes via domain actions + API. |
| Console (plans, billing ops) | — | `/console/` | **Console-only** | Platform operators / tenant admins. |

---

## Observability (shared)

With **`JSON_LOGS=true`**, root log handler enriches records with **`request_id`**, and after tenant resolution **`tenant_id`**, **`outlet_id`** (staff session or optional API header **`X-Outlet-Id`**), **`site_id`** when the staff/console branch picker is set (`staff_site_id` session), and **`user_id`** when authenticated (`OperationContextMiddleware` in `config/settings/base.py`).

---

## Maintenance

When shipping a feature:

1. Update the relevant row’s **Parity** and **Notes**.
2. If only API or only staff, say so explicitly to avoid drift.
3. Keep **`openapi.yaml`** / schema in sync for API columns (regenerate per `ARCHITECTURE.md`).

*Last updated: daily operations digest (CSV + optional email), offline queue catalog-stale UX, CSV exports (sales, finance), EFRIS staff queue, lodging tape chart, JSON `site_id`, finance API row.*
