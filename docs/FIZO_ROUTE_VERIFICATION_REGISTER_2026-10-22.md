# Fizo route-by-route implementation and verification register

Generated from Django URL definitions on 2026-10-22. A listed URL is not proof of working UI.

## Completion criteria

Each route needs approved layout, no obsolete styling references, role/business-line permission checks, functioning navigation and forms, mobile/tablet/desktop checks, automated tests, authenticated browser verification, and deployed production review.

`TODO` means not individually verified. `API` routes require contract/security testing instead of visual styling.

## Routes

### backend/apps/console/urls.py (55 entries)

| URL pattern | Kind | Status |
|---|---|---|
| `/console/` | UI | TODO |
| `/console/select-tenant/` | UI | TODO |
| `/console/platform/tenants/` | UI | TODO |
| `/console/platform/tenants/new/` | UI | TODO |
| `/console/platform/tenants/<uuid:tenant_id>/edit/` | UI | TODO |
| `/console/platform/tenants/<uuid:tenant_id>/control-plane/` | UI | TODO |
| `/console/platform/plans/` | UI | TODO |
| `/console/platform/plans/new/` | UI | TODO |
| `/console/platform/plans/<int:plan_id>/edit/` | UI | TODO |
| `/console/org/` | UI | TODO |
| `/console/org/setup/` | UI | TODO |
| `/console/org/menu/import/` | UI | TODO |
| `/console/org/setup/practice-sale/` | UI | TODO |
| `/console/org/setup/step-state/` | UI | TODO |
| `/console/org/sites/` | UI | TODO |
| `/console/org/sites/new/` | UI | TODO |
| `/console/org/sites/<uuid:site_id>/edit/` | UI | TODO |
| `/console/org/sites/<uuid:site_id>/outlets/` | UI | TODO |
| `/console/org/sites/<uuid:site_id>/outlets/new/` | UI | TODO |
| `/console/org/outlets/<uuid:outlet_id>/edit/` | UI | TODO |
| `/console/org/lodging/room-types/` | UI | TODO |
| `/console/org/lodging/room-types/new/` | UI | TODO |
| `/console/org/lodging/room-types/<uuid:room_type_id>/edit/` | UI | TODO |
| `/console/org/lodging/rooms/` | UI | TODO |
| `/console/org/lodging/rooms/new/` | UI | TODO |
| `/console/org/lodging/rooms/<uuid:room_id>/edit/` | UI | TODO |
| `/console/org/lodging/rates/` | UI | TODO |
| `/console/org/lodging/rates/new/` | UI | TODO |
| `/console/org/lodging/rates/<uuid:rate_id>/edit/` | UI | TODO |
| `/console/org/menu/modifier-groups/` | UI | TODO |
| `/console/org/menu/modifier-groups/new/` | UI | TODO |
| `/console/org/menu/modifier-groups/<uuid:group_id>/edit/` | UI | TODO |
| `/console/org/menu/modifier-groups/<uuid:group_id>/options/` | UI | TODO |
| `/console/org/menu/modifier-groups/<uuid:group_id>/options/new/` | UI | TODO |
| `/console/org/menu/modifier-groups/<uuid:group_id>/options/<uuid:option_id>/edit/` | UI | TODO |
| `/console/org/menu/categories/` | UI | TODO |
| `/console/org/menu/categories/new/` | UI | TODO |
| `/console/org/menu/categories/<uuid:category_id>/edit/` | UI | TODO |
| `/console/org/menu/items/` | UI | TODO |
| `/console/org/menu/items/new/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/edit/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/outlets/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/outlets/new/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/outlets/<int:link_id>/edit/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/outlets/<int:link_id>/delete/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/recipe/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/recipe/new/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/recipe/<uuid:line_id>/edit/` | UI | TODO |
| `/console/org/menu/items/<uuid:item_id>/recipe/<uuid:line_id>/delete/` | UI | TODO |
| `/console/org/services/` | UI | TODO |
| `/console/org/services/new/` | UI | TODO |
| `/console/org/services/<uuid:service_id>/edit/` | UI | TODO |
| `/console/org/services/<uuid:service_id>/packages/` | UI | TODO |
| `/console/org/services/<uuid:service_id>/packages/new/` | UI | TODO |
| `/console/org/services/<uuid:service_id>/packages/<uuid:option_id>/edit/` | UI | TODO |

### backend/apps/staff/urls.py (91 entries)

| URL pattern | Kind | Status |
|---|---|---|
| `/staff/notifications/` | UI | TODO |
| `/staff/search/` | UI | TODO |
| `/staff/inventory/intelligence/` | UI | TODO |
| `/staff/inventory/shelves/` | UI | TODO |
| `/staff/inventory/scale-labels/` | UI | TODO |
| `/staff/pos/wholesale-prices/` | UI | TODO |
| `/staff/pos/pickups/` | UI | TODO |
| `/staff/orders/<uuid:order_id>/display/` | UI | TODO |
| `/staff/lodging/night-audit/` | UI | TODO |
| `/staff/management/business-date/` | UI | TODO |
| `/staff/purchasing/balances/` | UI | TODO |
| `/staff/inventory/batches/` | UI | TODO |
| `/staff/customers/` | UI | TODO |
| `/staff/customers/new/` | UI | TODO |
| `/staff/customers/<uuid:customer_id>/` | UI | TODO |
| `/staff/management/sources/<str:kind>/<uuid:entity_id>/` | UI | TODO |
| `/staff/management/shifts/<uuid:shift_id>/` | UI | TODO |
| `/staff/management/` | UI | TODO |
| `/staff/login/` | UI | TODO |
| `/staff/logout/` | UI | TODO |
| `/staff/terminal/` | UI | TODO |
| `/staff/terminal/lock/` | UI | TODO |
| `/staff/terminal/pin/` | UI | TODO |
| `/staff/pending-approval/` | UI | TODO |
| `/staff/setup/prompt/dismiss/` | UI | TODO |
| `/staff/setup/prompt/resume/` | UI | TODO |
| `/staff/select-tenant/` | UI | TODO |
| `/staff/select-outlet/` | UI | TODO |
| `/staff/orders/` | UI | TODO |
| `/staff/orders/new/` | UI | TODO |
| `/staff/orders/<uuid:order_id>/` | UI | TODO |
| `/staff/orders/<uuid:order_id>/print/` | UI | TODO |
| `/staff/pos/workstations/` | UI | TODO |
| `/staff/pos/workstations/<uuid:workstation_id>/test/` | UI | TODO |
| `/staff/pos/workstations/<uuid:workstation_id>/browsers/` | UI | TODO |
| `/staff/pos/workstations/new/` | UI | TODO |
| `/staff/pos/workstations/<uuid:workstation_id>/edit/` | UI | TODO |
| `/staff/pos/shifts/` | UI | TODO |
| `/staff/tables/new/` | UI | TODO |
| `/staff/tables/<uuid:table_id>/edit/` | UI | TODO |
| `/staff/tables/` | UI | TODO |
| `/staff/kitchen/` | UI | TODO |
| `/staff/service-tv/` | UI | TODO |
| `/staff/menu/` | UI | TODO |
| `/staff/promotions/new/` | UI | TODO |
| `/staff/promotions/<uuid:promotion_id>/edit/` | UI | TODO |
| `/staff/promotions/<uuid:promotion_id>/` | UI | TODO |
| `/staff/promotions/` | UI | TODO |
| `/staff/reports/sales/` | UI | TODO |
| `/staff/finance/` | UI | TODO |
| `/staff/finance/new/` | UI | TODO |
| `/staff/finance/categories/new/` | UI | TODO |
| `/staff/pos/offline-queue/` | UI | TODO |
| `/staff/inventory/movements/new/` | UI | TODO |
| `/staff/inventory/movements/upload/` | UI | TODO |
| `/staff/inventory/movements/upload/template.csv` | UI | TODO |
| `/staff/inventory/movements/upload/errors.csv` | UI | TODO |
| `/staff/inventory/movements/` | UI | TODO |
| `/staff/inventory/transfer/` | UI | TODO |
| `/staff/inventory/transfer-receipts/` | UI | TODO |
| `/staff/inventory/counts/new/` | UI | TODO |
| `/staff/inventory/counts/<uuid:session_id>/` | UI | TODO |
| `/staff/inventory/counts/` | UI | TODO |
| `/staff/inventory/` | UI | TODO |
| `/staff/purchasing/suppliers/new/` | UI | TODO |
| `/staff/purchasing/suppliers/<uuid:supplier_id>/edit/` | UI | TODO |
| `/staff/purchasing/suppliers/` | UI | TODO |
| `/staff/purchasing/purchase-orders/new/` | UI | TODO |
| `/staff/purchasing/purchase-orders/<uuid:po_id>/` | UI | TODO |
| `/staff/purchasing/purchase-orders/` | UI | TODO |
| `/staff/lodging/select-site/` | UI | TODO |
| `/staff/lodging/reservations/new/` | UI | TODO |
| `/staff/lodging/reservations/<uuid:reservation_id>/` | UI | TODO |
| `/staff/lodging/availability/` | UI | TODO |
| `/staff/lodging/tape-chart/` | UI | TODO |
| `/staff/lodging/reservations/` | UI | TODO |
| `/staff/lodging/folios/<uuid:folio_id>/` | UI | TODO |
| `/staff/lodging/folios/` | UI | TODO |
| `/staff/lodging/rooms/` | UI | TODO |
| `/staff/lodging/housekeeping/` | UI | TODO |
| `/staff/lodging/maintenance/` | UI | TODO |
| `/staff/lodging/room-types/` | UI | TODO |
| `/staff/events/spaces/new/` | UI | TODO |
| `/staff/events/spaces/<uuid:space_id>/edit/` | UI | TODO |
| `/staff/events/spaces/` | UI | TODO |
| `/staff/events/bookings/new/` | UI | TODO |
| `/staff/events/bookings/<uuid:booking_id>/` | UI | TODO |
| `/staff/events/bookings/` | UI | TODO |
| `/staff/events/calendar/` | UI | TODO |
| `/staff/settings/` | UI | TODO |
| `/staff/` | UI | TODO |

### backend/apps/api/urls.py (21 entries)

| URL pattern | Kind | Status |
|---|---|---|
| `/api/v1/schema/` | API | TODO |
| `/api/v1/schema/swagger-ui/` | API | TODO |
| `/api/v1/schema/redoc/` | API | TODO |
| `/api/v1/health/` | API | TODO |
| `/api/v1/auth/token/` | API | TODO |
| `/api/v1/auth/token/refresh/` | API | TODO |
| `/api/v1/auth/signup/` | API | TODO |
| `/api/v1/auth/password/reset/` | API | TODO |
| `/api/v1/auth/password/reset/confirm/` | API | TODO |
| `/api/v1/me/` | API | TODO |
| `/api/v1/tenant/settings/` | API | TODO |
| `/api/v1/reports/sales-summary/` | API | TODO |
| `/api/v1/reports/operations-rollup/` | API | TODO |
| `/api/v1/integrations/payment-webhook/` | API | TODO |
| `/api/v1/kds/tickets/` | API | TODO |
| `/api/v1/pos/offline-sync/batch/` | API | TODO |
| `/api/v1/pos/offline-sync/` | API | TODO |
| `/api/v1/pos/catalog-version/` | API | TODO |
| `/api/v1/invites/` | API | TODO |
| `/api/v1/invites/accept/` | API | TODO |
| `/api/v1/` | API | TODO |

### backend/config/urls.py (7 entries)

| URL pattern | Kind | Status |
|---|---|---|
| `/` | SYSTEM | TODO |
| `/signup/` | SYSTEM | TODO |
| `/admin/` | SYSTEM | TODO |
| `/password-reset/confirm/` | SYSTEM | TODO |
| `/staff/` | SYSTEM | TODO |
| `/console/` | SYSTEM | TODO |
| `/api/v1/` | SYSTEM | TODO |

## Per-route evidence ledger

Before changing TODO to verified, record the commit, removed legacy CSS/template references, responsive screenshots, tests, permission scope, and live deployment verification.

## Implementation sequence

1. Setup wizard, overview, optional setup cards and linked configuration forms.
2. Staff setup links including invites, devices, purchasing and practice checkout.
3. Restaurant and bar POS, kitchen, tabs and settlement.
4. Hotel reservations, rooms, folios, housekeeping and audits.
5. Supermarket regression and business-line isolation.
6. Platform and API test coverage.
