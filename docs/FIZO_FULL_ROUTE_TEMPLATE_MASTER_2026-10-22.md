# Fizo Full Route and Template Master Inventory

Source: repository `origin/main`, 2026-10-22, inspected at commit d78e4537e97e6f66f70f683310b29858a29c3549.

Inventory covers every literal Django path declaration in four URLConf files, all DRF router registrations, every tracked HTML template, and the auto-generated route caveats. Classification is by path/name; actual business permissions and templates must be crosschecked against views and the runtime resolver.

Status of listed routes/templates is UNVERIFIED until testing and browser inspection. A route with angle-bracket parameters is a pattern, not a literal URL. Templates may be includes or bases rather than standalone screens.

## A. Django URL declarations

### backend/config/urls.py (7 declarations)

| # | URL/prefix | Business line / purpose |
|---:|---|---|
| 1 | `/` | Shared / cross-business |
| 2 | `/signup/` | Shared identity / staff / settings |
| 3 | `/admin/` | Platform / SaaS admin |
| 4 | `/password-reset/confirm/` | Shared identity / staff / settings |
| 5 | `/staff/` | Shared / cross-business |
| 6 | `/console/` | Shared / cross-business |
| 7 | `/api/v1/` | Shared API / integration |

### backend/apps/console/urls.py (55 declarations)

| # | URL/prefix | Business line / purpose |
|---:|---|---|
| 1 | `/console/` | Shared / cross-business |
| 2 | `/console/select-tenant/` | Platform / SaaS admin |
| 3 | `/console/platform/tenants/` | Platform / SaaS admin |
| 4 | `/console/platform/tenants/new/` | Platform / SaaS admin |
| 5 | `/console/platform/tenants/<uuid:tenant_id>/edit/` | Platform / SaaS admin |
| 6 | `/console/platform/tenants/<uuid:tenant_id>/control-plane/` | Platform / SaaS admin |
| 7 | `/console/platform/plans/` | Platform / SaaS admin |
| 8 | `/console/platform/plans/new/` | Platform / SaaS admin |
| 9 | `/console/platform/plans/<int:plan_id>/edit/` | Platform / SaaS admin |
| 10 | `/console/org/` | Shared / cross-business |
| 11 | `/console/org/setup/` | Shared / cross-business |
| 12 | `/console/org/menu/import/` | Restaurant / bar / retail catalogue |
| 13 | `/console/org/setup/practice-sale/` | Shared POS / payment |
| 14 | `/console/org/setup/step-state/` | Shared / cross-business |
| 15 | `/console/org/sites/` | Shared / cross-business |
| 16 | `/console/org/sites/new/` | Shared / cross-business |
| 17 | `/console/org/sites/<uuid:site_id>/edit/` | Shared / cross-business |
| 18 | `/console/org/sites/<uuid:site_id>/outlets/` | Shared / cross-business |
| 19 | `/console/org/sites/<uuid:site_id>/outlets/new/` | Shared / cross-business |
| 20 | `/console/org/outlets/<uuid:outlet_id>/edit/` | Shared / cross-business |
| 21 | `/console/org/lodging/room-types/` | Hotel / lodging |
| 22 | `/console/org/lodging/room-types/new/` | Hotel / lodging |
| 23 | `/console/org/lodging/room-types/<uuid:room_type_id>/edit/` | Hotel / lodging |
| 24 | `/console/org/lodging/rooms/` | Hotel / lodging |
| 25 | `/console/org/lodging/rooms/new/` | Hotel / lodging |
| 26 | `/console/org/lodging/rooms/<uuid:room_id>/edit/` | Hotel / lodging |
| 27 | `/console/org/lodging/rates/` | Hotel / lodging |
| 28 | `/console/org/lodging/rates/new/` | Hotel / lodging |
| 29 | `/console/org/lodging/rates/<uuid:rate_id>/edit/` | Hotel / lodging |
| 30 | `/console/org/menu/modifier-groups/` | Restaurant / bar / retail catalogue |
| 31 | `/console/org/menu/modifier-groups/new/` | Restaurant / bar / retail catalogue |
| 32 | `/console/org/menu/modifier-groups/<uuid:group_id>/edit/` | Restaurant / bar / retail catalogue |
| 33 | `/console/org/menu/modifier-groups/<uuid:group_id>/options/` | Restaurant / bar / retail catalogue |
| 34 | `/console/org/menu/modifier-groups/<uuid:group_id>/options/new/` | Restaurant / bar / retail catalogue |
| 35 | `/console/org/menu/modifier-groups/<uuid:group_id>/options/<uuid:option_id>/edit/` | Restaurant / bar / retail catalogue |
| 36 | `/console/org/menu/categories/` | Restaurant / bar / retail catalogue |
| 37 | `/console/org/menu/categories/new/` | Restaurant / bar / retail catalogue |
| 38 | `/console/org/menu/categories/<uuid:category_id>/edit/` | Restaurant / bar / retail catalogue |
| 39 | `/console/org/menu/items/` | Restaurant / bar / retail catalogue |
| 40 | `/console/org/menu/items/new/` | Restaurant / bar / retail catalogue |
| 41 | `/console/org/menu/items/<uuid:item_id>/edit/` | Restaurant / bar / retail catalogue |
| 42 | `/console/org/menu/items/<uuid:item_id>/outlets/` | Restaurant / bar / retail catalogue |
| 43 | `/console/org/menu/items/<uuid:item_id>/outlets/new/` | Restaurant / bar / retail catalogue |
| 44 | `/console/org/menu/items/<uuid:item_id>/outlets/<int:link_id>/edit/` | Restaurant / bar / retail catalogue |
| 45 | `/console/org/menu/items/<uuid:item_id>/outlets/<int:link_id>/delete/` | Restaurant / bar / retail catalogue |
| 46 | `/console/org/menu/items/<uuid:item_id>/recipe/` | Restaurant / bar / retail catalogue |
| 47 | `/console/org/menu/items/<uuid:item_id>/recipe/new/` | Restaurant / bar / retail catalogue |
| 48 | `/console/org/menu/items/<uuid:item_id>/recipe/<uuid:line_id>/edit/` | Restaurant / bar / retail catalogue |
| 49 | `/console/org/menu/items/<uuid:item_id>/recipe/<uuid:line_id>/delete/` | Restaurant / bar / retail catalogue |
| 50 | `/console/org/services/` | Services |
| 51 | `/console/org/services/new/` | Services |
| 52 | `/console/org/services/<uuid:service_id>/edit/` | Services |
| 53 | `/console/org/services/<uuid:service_id>/packages/` | Services |
| 54 | `/console/org/services/<uuid:service_id>/packages/new/` | Services |
| 55 | `/console/org/services/<uuid:service_id>/packages/<uuid:option_id>/edit/` | Services |

### backend/apps/staff/urls.py (91 declarations)

| # | URL/prefix | Business line / purpose |
|---:|---|---|
| 1 | `/staff/notifications/` | Shared / cross-business |
| 2 | `/staff/search/` | Shared / cross-business |
| 3 | `/staff/inventory/intelligence/` | Supermarket / retail and stock |
| 4 | `/staff/inventory/shelves/` | Supermarket / retail and stock |
| 5 | `/staff/inventory/scale-labels/` | Supermarket / retail and stock |
| 6 | `/staff/pos/wholesale-prices/` | Supermarket / retail and stock |
| 7 | `/staff/pos/pickups/` | Supermarket / retail and stock |
| 8 | `/staff/orders/<uuid:order_id>/display/` | Shared POS / payment |
| 9 | `/staff/lodging/night-audit/` | Hotel / lodging |
| 10 | `/staff/management/business-date/` | Shared / cross-business |
| 11 | `/staff/purchasing/balances/` | Supermarket / retail and stock |
| 12 | `/staff/inventory/batches/` | Supermarket / retail and stock |
| 13 | `/staff/customers/` | Shared / cross-business |
| 14 | `/staff/customers/new/` | Shared / cross-business |
| 15 | `/staff/customers/<uuid:customer_id>/` | Shared / cross-business |
| 16 | `/staff/management/sources/<str:kind>/<uuid:entity_id>/` | Shared / cross-business |
| 17 | `/staff/management/shifts/<uuid:shift_id>/` | Shared POS / payment |
| 18 | `/staff/management/` | Shared / cross-business |
| 19 | `/staff/login/` | Shared identity / staff / settings |
| 20 | `/staff/logout/` | Shared / cross-business |
| 21 | `/staff/terminal/` | Shared / cross-business |
| 22 | `/staff/terminal/lock/` | Shared identity / staff / settings |
| 23 | `/staff/terminal/pin/` | Shared identity / staff / settings |
| 24 | `/staff/pending-approval/` | Shared / cross-business |
| 25 | `/staff/setup/prompt/dismiss/` | Shared / cross-business |
| 26 | `/staff/setup/prompt/resume/` | Shared / cross-business |
| 27 | `/staff/select-tenant/` | Platform / SaaS admin |
| 28 | `/staff/select-outlet/` | Shared / cross-business |
| 29 | `/staff/orders/` | Shared POS / payment |
| 30 | `/staff/orders/new/` | Shared POS / payment |
| 31 | `/staff/orders/<uuid:order_id>/` | Shared POS / payment |
| 32 | `/staff/orders/<uuid:order_id>/print/` | Shared POS / payment |
| 33 | `/staff/pos/workstations/` | Shared POS / payment |
| 34 | `/staff/pos/workstations/<uuid:workstation_id>/test/` | Shared POS / payment |
| 35 | `/staff/pos/workstations/<uuid:workstation_id>/browsers/` | Shared POS / payment |
| 36 | `/staff/pos/workstations/new/` | Shared POS / payment |
| 37 | `/staff/pos/workstations/<uuid:workstation_id>/edit/` | Shared POS / payment |
| 38 | `/staff/pos/shifts/` | Shared POS / payment |
| 39 | `/staff/tables/new/` | Restaurant / bar / retail catalogue |
| 40 | `/staff/tables/<uuid:table_id>/edit/` | Restaurant / bar / retail catalogue |
| 41 | `/staff/tables/` | Restaurant / bar / retail catalogue |
| 42 | `/staff/kitchen/` | Restaurant / kitchen |
| 43 | `/staff/service-tv/` | Services |
| 44 | `/staff/menu/` | Restaurant / bar / retail catalogue |
| 45 | `/staff/promotions/new/` | Shared / cross-business |
| 46 | `/staff/promotions/<uuid:promotion_id>/edit/` | Shared / cross-business |
| 47 | `/staff/promotions/<uuid:promotion_id>/` | Shared / cross-business |
| 48 | `/staff/promotions/` | Shared / cross-business |
| 49 | `/staff/reports/sales/` | Shared finance / reports |
| 50 | `/staff/finance/` | Shared finance / reports |
| 51 | `/staff/finance/new/` | Shared finance / reports |
| 52 | `/staff/finance/categories/new/` | Shared finance / reports |
| 53 | `/staff/pos/offline-queue/` | Shared API / integration |
| 54 | `/staff/inventory/movements/new/` | Supermarket / retail and stock |
| 55 | `/staff/inventory/movements/upload/` | Supermarket / retail and stock |
| 56 | `/staff/inventory/movements/upload/template.csv` | Supermarket / retail and stock |
| 57 | `/staff/inventory/movements/upload/errors.csv` | Supermarket / retail and stock |
| 58 | `/staff/inventory/movements/` | Supermarket / retail and stock |
| 59 | `/staff/inventory/transfer/` | Supermarket / retail and stock |
| 60 | `/staff/inventory/transfer-receipts/` | Supermarket / retail and stock |
| 61 | `/staff/inventory/counts/new/` | Supermarket / retail and stock |
| 62 | `/staff/inventory/counts/<uuid:session_id>/` | Supermarket / retail and stock |
| 63 | `/staff/inventory/counts/` | Supermarket / retail and stock |
| 64 | `/staff/inventory/` | Supermarket / retail and stock |
| 65 | `/staff/purchasing/suppliers/new/` | Supermarket / retail and stock |
| 66 | `/staff/purchasing/suppliers/<uuid:supplier_id>/edit/` | Supermarket / retail and stock |
| 67 | `/staff/purchasing/suppliers/` | Supermarket / retail and stock |
| 68 | `/staff/purchasing/purchase-orders/new/` | Supermarket / retail and stock |
| 69 | `/staff/purchasing/purchase-orders/<uuid:po_id>/` | Supermarket / retail and stock |
| 70 | `/staff/purchasing/purchase-orders/` | Supermarket / retail and stock |
| 71 | `/staff/lodging/select-site/` | Hotel / lodging |
| 72 | `/staff/lodging/reservations/new/` | Hotel / lodging |
| 73 | `/staff/lodging/reservations/<uuid:reservation_id>/` | Hotel / lodging |
| 74 | `/staff/lodging/availability/` | Hotel / lodging |
| 75 | `/staff/lodging/tape-chart/` | Hotel / lodging |
| 76 | `/staff/lodging/reservations/` | Hotel / lodging |
| 77 | `/staff/lodging/folios/<uuid:folio_id>/` | Hotel / lodging |
| 78 | `/staff/lodging/folios/` | Hotel / lodging |
| 79 | `/staff/lodging/rooms/` | Hotel / lodging |
| 80 | `/staff/lodging/housekeeping/` | Hotel / lodging |
| 81 | `/staff/lodging/maintenance/` | Hotel / lodging |
| 82 | `/staff/lodging/room-types/` | Hotel / lodging |
| 83 | `/staff/events/spaces/new/` | Services |
| 84 | `/staff/events/spaces/<uuid:space_id>/edit/` | Services |
| 85 | `/staff/events/spaces/` | Services |
| 86 | `/staff/events/bookings/new/` | Events |
| 87 | `/staff/events/bookings/<uuid:booking_id>/` | Events |
| 88 | `/staff/events/bookings/` | Events |
| 89 | `/staff/events/calendar/` | Events |
| 90 | `/staff/settings/` | Shared identity / staff / settings |
| 91 | `/staff/` | Shared / cross-business |

### backend/apps/api/urls.py (21 declarations)

| # | URL/prefix | Business line / purpose |
|---:|---|---|
| 1 | `/api/v1/schema/` | Shared API / integration |
| 2 | `/api/v1/schema/swagger-ui/` | Shared API / integration |
| 3 | `/api/v1/schema/redoc/` | Shared API / integration |
| 4 | `/api/v1/health/` | Shared API / integration |
| 5 | `/api/v1/auth/token/` | Shared identity / staff / settings |
| 6 | `/api/v1/auth/token/refresh/` | Shared identity / staff / settings |
| 7 | `/api/v1/auth/signup/` | Shared identity / staff / settings |
| 8 | `/api/v1/auth/password/reset/` | Shared identity / staff / settings |
| 9 | `/api/v1/auth/password/reset/confirm/` | Shared identity / staff / settings |
| 10 | `/api/v1/me/` | Shared API / integration |
| 11 | `/api/v1/tenant/settings/` | Platform / SaaS admin |
| 12 | `/api/v1/reports/sales-summary/` | Shared finance / reports |
| 13 | `/api/v1/reports/operations-rollup/` | Shared finance / reports |
| 14 | `/api/v1/integrations/payment-webhook/` | Shared API / integration |
| 15 | `/api/v1/kds/tickets/` | Restaurant / kitchen |
| 16 | `/api/v1/pos/offline-sync/batch/` | Shared API / integration |
| 17 | `/api/v1/pos/offline-sync/` | Shared API / integration |
| 18 | `/api/v1/pos/catalog-version/` | Shared API / integration |
| 19 | `/api/v1/invites/` | Shared identity / staff / settings |
| 20 | `/api/v1/invites/accept/` | Shared identity / staff / settings |
| 21 | `/api/v1/` | Shared API / integration |

Total explicit path declarations: **174** (including root redirects and route mounts).

## B. DRF router-generated API resource families

Each registration generates collection/detail and possibly action endpoints. Expand the precise set via Django's URL resolver.

| # | API resource prefix | Business line / purpose |
|---:|---|---|
| 1 | `/api/v1/customers/` | Shared / cross-business |
| 2 | `/api/v1/menu/categories/` | Restaurant / bar / retail catalogue |
| 3 | `/api/v1/menu/items/` | Restaurant / bar / retail catalogue |
| 4 | `/api/v1/menu/promotions/` | Restaurant / bar / retail catalogue |
| 5 | `/api/v1/menu/modifier-groups/` | Restaurant / bar / retail catalogue |
| 6 | `/api/v1/menu/modifier-options/` | Restaurant / bar / retail catalogue |
| 7 | `/api/v1/events/spaces/` | Services |
| 8 | `/api/v1/events/bookings/` | Events |
| 9 | `/api/v1/finance/categories/` | Shared finance / reports |
| 10 | `/api/v1/finance/entries/` | Shared finance / reports |
| 11 | `/api/v1/integrations/links/` | Shared API / integration |
| 12 | `/api/v1/tables/` | Restaurant / bar / retail catalogue |
| 13 | `/api/v1/pos/shifts/` | Shared POS / payment |
| 14 | `/api/v1/orders/` | Shared POS / payment |
| 15 | `/api/v1/stock/balances/` | Supermarket / retail and stock |
| 16 | `/api/v1/stock/shelves/` | Supermarket / retail and stock |
| 17 | `/api/v1/stock/movements/` | Supermarket / retail and stock |
| 18 | `/api/v1/stock/transfers/` | Supermarket / retail and stock |
| 19 | `/api/v1/stock/count-sessions/` | Supermarket / retail and stock |
| 20 | `/api/v1/purchasing/suppliers/` | Supermarket / retail and stock |
| 21 | `/api/v1/purchasing/purchase-orders/` | Supermarket / retail and stock |
| 22 | `/api/v1/lodging/room-types/` | Hotel / lodging |
| 23 | `/api/v1/lodging/rate-windows/` | Hotel / lodging |
| 24 | `/api/v1/lodging/rooms/` | Hotel / lodging |
| 25 | `/api/v1/lodging/reservations/` | Hotel / lodging |
| 26 | `/api/v1/lodging/folios/` | Hotel / lodging |
| 27 | `/api/v1/audit-events/` | Platform / SaaS admin |

Router resource families: **27**.

## C. Every tracked HTML template

Includes standalone pages, partials, layouts, receipts and specialty displays; not all are separately navigable URLs.

| # | Template path | Business line / purpose | Template kind |
|---:|---|---|---|
| 1 | `backend/apps/console/templates/console/base.html` | Shared / cross-business | Base / include |
| 2 | `backend/apps/console/templates/console/includes/fizo_nav.html` | Shared / cross-business | Base / include |
| 3 | `backend/apps/console/templates/console/includes/fizo_sidebar.html` | Shared / cross-business | Base / include |
| 4 | `backend/apps/console/templates/console/includes/nav.html` | Shared / cross-business | Base / include |
| 5 | `backend/apps/console/templates/console/includes/sidebar.html` | Shared / cross-business | Base / include |
| 6 | `backend/apps/console/templates/console/index.html` | Shared / cross-business | Page / form |
| 7 | `backend/apps/console/templates/console/org/catalog_import.html` | Shared / cross-business | Page / form |
| 8 | `backend/apps/console/templates/console/org/menu_category_form.html` | Restaurant / bar / retail catalogue | Page / form |
| 9 | `backend/apps/console/templates/console/org/menu_category_list.html` | Restaurant / bar / retail catalogue | Page / form |
| 10 | `backend/apps/console/templates/console/org/menu_item_form.html` | Restaurant / bar / retail catalogue | Page / form |
| 11 | `backend/apps/console/templates/console/org/menu_item_list.html` | Restaurant / bar / retail catalogue | Page / form |
| 12 | `backend/apps/console/templates/console/org/menu_item_outlet_confirm_delete.html` | Restaurant / bar / retail catalogue | Page / form |
| 13 | `backend/apps/console/templates/console/org/menu_item_outlet_form.html` | Restaurant / bar / retail catalogue | Page / form |
| 14 | `backend/apps/console/templates/console/org/menu_item_outlet_list.html` | Restaurant / bar / retail catalogue | Page / form |
| 15 | `backend/apps/console/templates/console/org/menu_item_recipe_confirm_delete.html` | Restaurant / bar / retail catalogue | Page / form |
| 16 | `backend/apps/console/templates/console/org/menu_item_recipe_form.html` | Restaurant / bar / retail catalogue | Page / form |
| 17 | `backend/apps/console/templates/console/org/menu_item_recipe_list.html` | Restaurant / bar / retail catalogue | Page / form |
| 18 | `backend/apps/console/templates/console/org/modifier_group_form.html` | Restaurant / bar / retail catalogue | Page / form |
| 19 | `backend/apps/console/templates/console/org/modifier_group_list.html` | Restaurant / bar / retail catalogue | Page / form |
| 20 | `backend/apps/console/templates/console/org/modifier_option_form.html` | Restaurant / bar / retail catalogue | Page / form |
| 21 | `backend/apps/console/templates/console/org/modifier_option_list.html` | Restaurant / bar / retail catalogue | Page / form |
| 22 | `backend/apps/console/templates/console/org/outlet_form.html` | Shared / cross-business | Page / form |
| 23 | `backend/apps/console/templates/console/org/outlet_list.html` | Shared / cross-business | Page / form |
| 24 | `backend/apps/console/templates/console/org/overview.html` | Shared / cross-business | Page / form |
| 25 | `backend/apps/console/templates/console/org/practice_sale.html` | Shared POS / payment | Page / form |
| 26 | `backend/apps/console/templates/console/org/room_form.html` | Hotel / lodging | Page / form |
| 27 | `backend/apps/console/templates/console/org/room_list.html` | Hotel / lodging | Page / form |
| 28 | `backend/apps/console/templates/console/org/room_rate_form.html` | Hotel / lodging | Page / form |
| 29 | `backend/apps/console/templates/console/org/room_rate_list.html` | Hotel / lodging | Page / form |
| 30 | `backend/apps/console/templates/console/org/room_type_form.html` | Hotel / lodging | Page / form |
| 31 | `backend/apps/console/templates/console/org/room_type_list.html` | Hotel / lodging | Page / form |
| 32 | `backend/apps/console/templates/console/org/service_offering_form.html` | Services | Page / form |
| 33 | `backend/apps/console/templates/console/org/service_offering_list.html` | Services | Page / form |
| 34 | `backend/apps/console/templates/console/org/service_offering_option_form.html` | Services | Page / form |
| 35 | `backend/apps/console/templates/console/org/service_offering_option_list.html` | Services | Page / form |
| 36 | `backend/apps/console/templates/console/org/setup_wizard.html` | Shared / cross-business | Page / form |
| 37 | `backend/apps/console/templates/console/org/site_form.html` | Shared / cross-business | Page / form |
| 38 | `backend/apps/console/templates/console/org/site_list.html` | Shared / cross-business | Page / form |
| 39 | `backend/apps/console/templates/console/platform/plan_form.html` | Platform / SaaS admin | Page / form |
| 40 | `backend/apps/console/templates/console/platform/plan_list.html` | Platform / SaaS admin | Page / form |
| 41 | `backend/apps/console/templates/console/platform/tenant_control_plane.html` | Platform / SaaS admin | Page / form |
| 42 | `backend/apps/console/templates/console/platform/tenant_form.html` | Platform / SaaS admin | Page / form |
| 43 | `backend/apps/console/templates/console/platform/tenant_list.html` | Platform / SaaS admin | Page / form |
| 44 | `backend/apps/staff/templates/staff/base.html` | Shared / cross-business | Base / include |
| 45 | `backend/apps/staff/templates/staff/business_date.html` | Shared / cross-business | Page / form |
| 46 | `backend/apps/staff/templates/staff/customers/detail.html` | Shared / cross-business | Page / form |
| 47 | `backend/apps/staff/templates/staff/customers/form.html` | Shared / cross-business | Page / form |
| 48 | `backend/apps/staff/templates/staff/customers/list.html` | Shared / cross-business | Page / form |
| 49 | `backend/apps/staff/templates/staff/dashboard.html` | Shared / cross-business | Page / form |
| 50 | `backend/apps/staff/templates/staff/events/booking_detail.html` | Events | Page / form |
| 51 | `backend/apps/staff/templates/staff/events/booking_form.html` | Events | Page / form |
| 52 | `backend/apps/staff/templates/staff/events/bookings_list.html` | Events | Page / form |
| 53 | `backend/apps/staff/templates/staff/events/calendar_week.html` | Events | Page / form |
| 54 | `backend/apps/staff/templates/staff/events/includes/subnav.html` | Events | Base / include |
| 55 | `backend/apps/staff/templates/staff/events/space_form.html` | Services | Page / form |
| 56 | `backend/apps/staff/templates/staff/events/spaces_list.html` | Services | Page / form |
| 57 | `backend/apps/staff/templates/staff/finance/category_form.html` | Shared finance / reports | Page / form |
| 58 | `backend/apps/staff/templates/staff/finance/entries_list.html` | Shared finance / reports | Page / form |
| 59 | `backend/apps/staff/templates/staff/finance/entry_form.html` | Shared finance / reports | Page / form |
| 60 | `backend/apps/staff/templates/staff/includes/documentary_photo.html` | Shared / cross-business | Base / include |
| 61 | `backend/apps/staff/templates/staff/includes/empty_state.html` | Shared / cross-business | Base / include |
| 62 | `backend/apps/staff/templates/staff/includes/exception_assessment_fields.html` | Shared / cross-business | Base / include |
| 63 | `backend/apps/staff/templates/staff/includes/fizo_pos_catalogue.html` | Shared POS / payment | Base / include |
| 64 | `backend/apps/staff/templates/staff/includes/form_errors_block.html` | Shared identity / staff / settings | Base / include |
| 65 | `backend/apps/staff/templates/staff/includes/grocery_owner_dashboard.html` | Shared / cross-business | Base / include |
| 66 | `backend/apps/staff/templates/staff/includes/messages.html` | Shared / cross-business | Base / include |
| 67 | `backend/apps/staff/templates/staff/includes/nav.html` | Shared / cross-business | Base / include |
| 68 | `backend/apps/staff/templates/staff/includes/orders_lanes.html` | Shared POS / payment | Base / include |
| 69 | `backend/apps/staff/templates/staff/includes/service_tv_ticket.html` | Services | Base / include |
| 70 | `backend/apps/staff/templates/staff/includes/sidebar.html` | Shared / cross-business | Base / include |
| 71 | `backend/apps/staff/templates/staff/includes/workspace_subnav.html` | Services | Base / include |
| 72 | `backend/apps/staff/templates/staff/inventory/balances.html` | Supermarket / retail and stock | Page / form |
| 73 | `backend/apps/staff/templates/staff/inventory/batches.html` | Supermarket / retail and stock | Page / form |
| 74 | `backend/apps/staff/templates/staff/inventory/count_create.html` | Supermarket / retail and stock | Page / form |
| 75 | `backend/apps/staff/templates/staff/inventory/count_detail.html` | Supermarket / retail and stock | Page / form |
| 76 | `backend/apps/staff/templates/staff/inventory/counts_list.html` | Supermarket / retail and stock | Page / form |
| 77 | `backend/apps/staff/templates/staff/inventory/includes/subnav.html` | Supermarket / retail and stock | Base / include |
| 78 | `backend/apps/staff/templates/staff/inventory/intelligence.html` | Supermarket / retail and stock | Page / form |
| 79 | `backend/apps/staff/templates/staff/inventory/movement_form.html` | Supermarket / retail and stock | Page / form |
| 80 | `backend/apps/staff/templates/staff/inventory/movement_upload.html` | Supermarket / retail and stock | Page / form |
| 81 | `backend/apps/staff/templates/staff/inventory/movements.html` | Supermarket / retail and stock | Page / form |
| 82 | `backend/apps/staff/templates/staff/inventory/scale_labels.html` | Supermarket / retail and stock | Page / form |
| 83 | `backend/apps/staff/templates/staff/inventory/shelves.html` | Supermarket / retail and stock | Page / form |
| 84 | `backend/apps/staff/templates/staff/inventory/transfer_form.html` | Supermarket / retail and stock | Page / form |
| 85 | `backend/apps/staff/templates/staff/inventory/transfer_receipts.html` | Supermarket / retail and stock | Specialized display |
| 86 | `backend/apps/staff/templates/staff/kds/queue.html` | Restaurant / kitchen | Specialized display |
| 87 | `backend/apps/staff/templates/staff/lodging/availability.html` | Hotel / lodging | Page / form |
| 88 | `backend/apps/staff/templates/staff/lodging/folio_detail.html` | Hotel / lodging | Page / form |
| 89 | `backend/apps/staff/templates/staff/lodging/folios_list.html` | Hotel / lodging | Page / form |
| 90 | `backend/apps/staff/templates/staff/lodging/housekeeping.html` | Hotel / lodging | Page / form |
| 91 | `backend/apps/staff/templates/staff/lodging/includes/subnav.html` | Hotel / lodging | Base / include |
| 92 | `backend/apps/staff/templates/staff/lodging/maintenance.html` | Hotel / lodging | Page / form |
| 93 | `backend/apps/staff/templates/staff/lodging/night_audit.html` | Hotel / lodging | Page / form |
| 94 | `backend/apps/staff/templates/staff/lodging/reservation_detail.html` | Hotel / lodging | Page / form |
| 95 | `backend/apps/staff/templates/staff/lodging/reservation_form.html` | Hotel / lodging | Page / form |
| 96 | `backend/apps/staff/templates/staff/lodging/reservations_list.html` | Hotel / lodging | Page / form |
| 97 | `backend/apps/staff/templates/staff/lodging/room_types_list.html` | Hotel / lodging | Page / form |
| 98 | `backend/apps/staff/templates/staff/lodging/rooms_list.html` | Hotel / lodging | Page / form |
| 99 | `backend/apps/staff/templates/staff/lodging/tape_chart.html` | Hotel / lodging | Page / form |
| 100 | `backend/apps/staff/templates/staff/login.html` | Shared identity / staff / settings | Page / form |
| 101 | `backend/apps/staff/templates/staff/management.html` | Shared / cross-business | Page / form |
| 102 | `backend/apps/staff/templates/staff/management_shift.html` | Shared POS / payment | Page / form |
| 103 | `backend/apps/staff/templates/staff/management_source.html` | Shared / cross-business | Page / form |
| 104 | `backend/apps/staff/templates/staff/menu_list.html` | Restaurant / bar / retail catalogue | Page / form |
| 105 | `backend/apps/staff/templates/staff/notifications/inbox.html` | Shared / cross-business | Page / form |
| 106 | `backend/apps/staff/templates/staff/order_detail.html` | Shared POS / payment | Page / form |
| 107 | `backend/apps/staff/templates/staff/order_detail_supermarket.html` | Shared POS / payment | Page / form |
| 108 | `backend/apps/staff/templates/staff/order_print.html` | Shared POS / payment | Specialized display |
| 109 | `backend/apps/staff/templates/staff/orders_list.html` | Shared POS / payment | Page / form |
| 110 | `backend/apps/staff/templates/staff/pending_approval.html` | Shared / cross-business | Page / form |
| 111 | `backend/apps/staff/templates/staff/pin_setup.html` | Shared identity / staff / settings | Page / form |
| 112 | `backend/apps/staff/templates/staff/pos/customer_display.html` | Shared POS / payment | Specialized display |
| 113 | `backend/apps/staff/templates/staff/pos/offline_queue.html` | Shared API / integration | Page / form |
| 114 | `backend/apps/staff/templates/staff/pos/pickups.html` | Supermarket / retail and stock | Page / form |
| 115 | `backend/apps/staff/templates/staff/pos/wholesale_pricing.html` | Supermarket / retail and stock | Page / form |
| 116 | `backend/apps/staff/templates/staff/pos_shifts.html` | Shared POS / payment | Page / form |
| 117 | `backend/apps/staff/templates/staff/promotion_detail.html` | Shared / cross-business | Page / form |
| 118 | `backend/apps/staff/templates/staff/promotion_form.html` | Shared / cross-business | Page / form |
| 119 | `backend/apps/staff/templates/staff/promotions_list.html` | Shared / cross-business | Page / form |
| 120 | `backend/apps/staff/templates/staff/purchasing/includes/subnav.html` | Supermarket / retail and stock | Base / include |
| 121 | `backend/apps/staff/templates/staff/purchasing/purchase_order_create.html` | Supermarket / retail and stock | Page / form |
| 122 | `backend/apps/staff/templates/staff/purchasing/purchase_order_detail.html` | Supermarket / retail and stock | Page / form |
| 123 | `backend/apps/staff/templates/staff/purchasing/purchase_orders_list.html` | Supermarket / retail and stock | Page / form |
| 124 | `backend/apps/staff/templates/staff/purchasing/supplier_balances.html` | Supermarket / retail and stock | Page / form |
| 125 | `backend/apps/staff/templates/staff/purchasing/supplier_form.html` | Supermarket / retail and stock | Page / form |
| 126 | `backend/apps/staff/templates/staff/purchasing/suppliers_list.html` | Supermarket / retail and stock | Page / form |
| 127 | `backend/apps/staff/templates/staff/sales_summary.html` | Shared POS / payment | Page / form |
| 128 | `backend/apps/staff/templates/staff/search/index.html` | Shared / cross-business | Page / form |
| 129 | `backend/apps/staff/templates/staff/search/palette.html` | Shared / cross-business | Base / include |
| 130 | `backend/apps/staff/templates/staff/service_tv.html` | Services | Specialized display |
| 131 | `backend/apps/staff/templates/staff/settings/audit_log.html` | Shared identity / staff / settings | Page / form |
| 132 | `backend/apps/staff/templates/staff/settings/branding.html` | Shared identity / staff / settings | Page / form |
| 133 | `backend/apps/staff/templates/staff/settings/efris_settings.html` | Shared identity / staff / settings | Page / form |
| 134 | `backend/apps/staff/templates/staff/settings/includes/subnav.html` | Shared identity / staff / settings | Base / include |
| 135 | `backend/apps/staff/templates/staff/settings/integration_form.html` | Shared identity / staff / settings | Page / form |
| 136 | `backend/apps/staff/templates/staff/settings/integrations_list.html` | Shared identity / staff / settings | Page / form |
| 137 | `backend/apps/staff/templates/staff/settings/invite_form.html` | Shared identity / staff / settings | Page / form |
| 138 | `backend/apps/staff/templates/staff/settings/invites_list.html` | Shared identity / staff / settings | Page / form |
| 139 | `backend/apps/staff/templates/staff/settings/member_form.html` | Shared identity / staff / settings | Page / form |
| 140 | `backend/apps/staff/templates/staff/settings/members_list.html` | Shared identity / staff / settings | Page / form |
| 141 | `backend/apps/staff/templates/staff/settings/modules.html` | Shared identity / staff / settings | Page / form |
| 142 | `backend/apps/staff/templates/staff/settings/owner_reports.html` | Shared finance / reports | Page / form |
| 143 | `backend/apps/staff/templates/staff/settings/worker_form.html` | Shared identity / staff / settings | Page / form |
| 144 | `backend/apps/staff/templates/staff/table_form.html` | Restaurant / bar / retail catalogue | Page / form |
| 145 | `backend/apps/staff/templates/staff/tables_list.html` | Restaurant / bar / retail catalogue | Page / form |
| 146 | `backend/apps/staff/templates/staff/terminal.html` | Shared / cross-business | Page / form |
| 147 | `backend/apps/staff/templates/staff/workstation_form.html` | Shared / cross-business | Page / form |
| 148 | `backend/apps/staff/templates/staff/workstation_pair.html` | Shared / cross-business | Page / form |
| 149 | `backend/apps/staff/templates/staff/workstation_test.html` | Shared / cross-business | Page / form |
| 150 | `backend/apps/staff/templates/staff/workstations.html` | Shared / cross-business | Page / form |
| 151 | `backend/templates/includes/phase4_control_panel.html` | Shared / cross-business | Base / include |
| 152 | `backend/templates/password_reset/confirm.html` | Shared identity / staff / settings | Page / form |
| 153 | `backend/templates/public/signup.html` | Shared identity / staff / settings | Page / form |

Total tracked HTML templates: **153**.

## D. Dynamically generated and non-HTML routes

- Django admin at `/admin/` generates site index, authentication, and each registered model's list/create/change/delete/history URLs and actions. A running Django app registry is required to enumerate these accurately.
- The 27 registered API ViewSets generate additional method- and action-dependent URL patterns. Use `get_resolver()` and the router registry to enumerate the final routes.
- CSV exports, PDF/receipts, device checks, background jobs, websocket consumers, and non-HTML endpoints need workflow/security tests but may not have an HTML template.

## E. Mandatory per-screen acceptance

Before DONE: resolved route name, view and template chain confirmed; target business line and permissions verified; old styles removed; all controls functional; desktop/tablet/mobile tested; automated tests run; authenticated production browser inspected; commit SHA and screenshot captured.

## F. Work sequence

1. Shared staff and console shell, authentication, role-based navigation.
2. Supermarket cashier and owner overview; stock, purchasing, receipts.
3. Restaurant tables and ordering; menu/modifiers and KDS.
4. Bar tabs, drinks and settlement.
5. Hotel reservations, rooms, folios, housekeeping, audits.
6. Shared staff, services/events, finance/reports, platform console.
7. URL resolver exact enumeration and final per-route verification.

## G. Runtime visual-screen crosswalk (added 2026-10-22)

Run the updated inventory command in the configured Django production environment:

```bash
cd /home/admin/Bar-Hotel-POS/backend
set -a
source /etc/leosoft-pos/pos.env
set +a
../.venv/bin/python ../scripts/inventory_fizo_routes.py
```

It now generates three files:

- `fizo_resolved_routes.csv`: every Django-resolved URL pattern, including Django admin and DRF routes. Contains route name, view source, declared template (when available), and route type.
- `fizo_templates.csv`: every tracked HTML template.
- `fizo_visual_screen_register.csv`: candidate human-facing routes, joined to their view and declared template when statically available, with an explicit `NEEDS VIEW TRACE` marker otherwise.

**This does not magically verify or redesign the pages.** A URL can render different templates according to role, business line, permissions or outlet. The `declared_template` field is only an inspectable class attribute, not a guaranteed runtime template chain. Admin and API views remain in the resolved inventory and need separate functional inspection. The generated register is a starting work queue, not a claimed completion report.

### Status rules and evidence required

- `NOT VERIFIED`: route identified but no full user-flow acceptance evidence.
- `IN DESIGN`: layout rebuilt with the approved Fizo reference.
- `FUNCTIONALLY TESTED`: permitted and denied roles and form/action behavior exercised against test fixtures.
- `BROWSER VERIFIED`: authenticated desktop, tablet and phone layouts reviewed against the reference; screenshots captured.
- `PRODUCTION VERIFIED`: deployed assets, live navigation, full workflow and tenant isolation confirmed.
- Only the final status above constitutes a finished screen. Keep PR/commit, screenshot, test command, tester and deployment revision with each entry.

### Priority screens for the clean redesign

1. Shared staff/console navigation and authentication for all roles.
2. Supermarket cashier checkout, product catalogue, basket, hold, tender, receipt and shift.
3. Supermarket management, catalogue, stock, purchasing and receiving.
4. Restaurant floor status (not merely table setup), ordering, modifiers, KDS and settlement.
5. Bar tabs, drinks, shared orders and closing shifts.
6. Hotel front desk, room availability, reservations, occupancy, housekeeping, folios, night audit.
7. Shared reports, finance, role management, services/events and platform-console pages.

The route inventory is the source of truth for scope. Previously committed template/CSS changes remain `NOT VERIFIED` until tested and visually accepted.
