# Route Owner Inventory

This inventory records route ownership, allowed request methods, access boundary, rendered surface, and important service/data dependencies. It is deliberately tied to the actual URL modules and view owners rather than treating URL names as proof of authorization.

## `backend/config/urls.py`

| Path / name | Owner | Methods | Access / permission boundary | Surface / dependency |
| --- | --- | --- | --- | --- |
| `/media/products/<path:path>` · `public-product-media` | `config.urls.public_product_media` | GET, HEAD | Public product-display asset only. Resolved path must remain inside `MEDIA_ROOT/products`; missing/out-of-root files return 404. | `FileResponse`; MIME guessed from filename; public cache header + `nosniff`. Reverse proxy may serve the same media root in production. |
| `/` · `root-entry` | `config.urls.root_entry` | GET, HEAD | Public entry. Authenticated users go to staff dashboard; anonymous users go to staff login. | Redirect only; no direct template. |
| `/signup/` · `public-signup` | `apps.api.web_signup.PublicSignupView` | GET, POST | Public onboarding. POST validates email/workspace/password/business lines; successful creation logs in the new user and binds selected tenant in session. | `public/signup.html`; `create_pending_workspace_signup`; Django login; `STAFF_SESSION_TENANT_KEY`. |
| `/password-reset/` · `staff-password-reset-request` | `StaffPasswordRecoveryRequestView` | GET, POST | Public recovery request; account existence is not disclosed. Request is rate-bounded by IP+email fingerprint. | `password_reset/request.html`; cache rate guard; `request_password_reset_for_email`; `never_cache`. |
| `/password-reset/confirm/` · `staff-password-reset-confirm` | `StaffPasswordResetConfirmView` | GET, POST | Public token confirmation. Requires uid/token; POST delegates password validation and token consumption to shared reset core. | `password_reset/confirm.html`; `attempt_password_reset_confirm`; `never_cache`. |
| `/admin/` | Django admin site configured by `configure_platform_admin_site` | Framework-defined | Django admin authentication plus configured platform/admin permissions. | Admin site URLs; no independent public owner. |
| `/staff/` | include `apps.staff.urls` | Delegated | Staff tenant/session/membership boundaries are owned by the included views/mixins. | See staff route inventory section when completed. |
| `/console/` | include `apps.console.urls` | Delegated | Console/platform/organization permissions are owned by included views/mixins. | See console route inventory section when completed. |
| `/api/v1/` | include `apps.api.urls` | Delegated | API authentication/permissions/throttles are owned by DRF views/viewsets. | See API route inventory section when completed. |

### Config-route regression contract

- `root-entry` and `public-product-media` use `require_safe`, so mutation methods do not accidentally execute read-only behavior.
- Product media resolves with `Path.resolve(strict=True)` and rejects traversal outside the products root.
- Product media response keeps public cache semantics and `X-Content-Type-Options: nosniff`.
- Signup and password reset remain POST-capable because they intentionally mutate onboarding/authentication state.


## `backend/apps/api/urls.py`

The API root is `/api/v1/`. Tenant-bound routes require a valid authenticated membership plus `X-Tenant-Id` through `HasTenantContext` unless explicitly listed as public. Module-gated families use the same staff-module resolver as the UI; role-specific viewsets may narrow reads, writes or actions further.

| Path / router family | Owner | Methods | Access / permission boundary | Main dependencies / notes |
| --- | --- | --- | --- | --- |
| `schema/`, `schema/swagger-ui/`, `schema/redoc/` | drf-spectacular views | GET, HEAD | Schema tooling; framework auth behavior. | OpenAPI generation from registered API owners. |
| `health/` · `api-health` | `apps.api.views.health` | GET | Public `AllowAny`. | Static service-health JSON. |
| `auth/token/`, `auth/token/refresh/` | throttled SimpleJWT views | POST | Public credential/token exchange with scoped throttles. | SimpleJWT; `jwt_obtain` / `jwt_refresh` throttle scopes. |
| `auth/signup/` | `PublicSignupView` | POST | Public `AllowAny`, throttled. | Pending workspace signup service; no tenant context required. |
| `auth/password/reset/`, `auth/password/reset/confirm/` | password reset API views | POST | Public `AllowAny`, dedicated reset throttles. | Shared password-reset core; non-disclosing request flow. |
| `me/` | `MeView` | GET | Authenticated user. | `MeSerializer`; no tenant mutation. |
| `tenant/settings/` | `TenantSettingsView` | GET, PATCH | Auth + tenant context; writes require owner/tenant-admin capability and non-read-only role. | `TenantSettingsSerializer`. |
| `reports/sales-summary/`, `reports/operations-rollup/` | report API views | GET | Auth + tenant + POS module + `CanViewSalesReports`; outlet IDs are scoped to membership. | Payments/refunds aggregation; explicit date/outlet parsing. |
| `integrations/payment-webhook/` | `PaymentProviderWebhookView` | POST | Public transport endpoint, but requires configured shared secret + tenant header; constant-time secret compare. | Cache idempotency key, durable audit event; failed audit releases key; unhandled internals are redacted by API exception handler. |
| `kds/tickets/` | `KdsTicketView` | GET, POST | Auth + tenant + kitchen module + `CanUseKds`; kitchen/bar station boundaries enforced. | Order/KDS status services and manager actions. |
| `pos/offline-sync/`, `pos/offline-sync/batch/` | offline queue API views | POST | Auth + tenant + POS module + shared POS sales-operator roles; throttled. | Offline operation validation, catalogue-staleness checks, idempotent replay handling. |
| `pos/catalog-version/` | `PosCatalogVersionView` | GET | Auth + tenant + POS module; throttled. | Read-only catalogue version/fingerprint for offline clients. |
| `invites/` | `InviteCreateView` | POST | Auth + tenant + owner/tenant-admin settings capability; throttled. | Role policy, site/outlet scope validation, invite service. |
| `invites/accept/` | `InviteAcceptView` | POST | Public `AllowAny`, throttled; token/expiry checked. | User creation/password set, membership/site/outlet assignment. |
| `customers/` | `CustomerDirectoryViewSet` | GET, HEAD | Auth + tenant; queryset additionally requires `can_manage_customers` and `visible_customers`. | Read-only customer profile directory; no mutation route. |
| `menu/categories/`, `menu/items/`, modifier and promotion families | catalog viewsets | Router GET/POST/PUT/PATCH/DELETE as declared | Auth + tenant + POS module. Safe reads are available to tenant clients; shared catalogue mutations require owner/tenant admin via `CanManageCatalog`. | Tenant-scoped catalogue, recipe/resolve actions, promotion/modifier models. |
| `events/spaces/`, `events/bookings/` | event viewsets | Router reads/writes; booking quote/payment actions | Auth + tenant + events module + view role; unsafe actions use event manager permission. | Site-scoped event inventory, quotes and payments. |
| `finance/categories/`, `finance/entries/` | finance viewsets | Categories GET/POST/PATCH; entries GET/POST | Auth + tenant + finance module + finance-view roles; writes require finance managers; accountant stays read-only. | Site-scoped cashbook/category serializers and validation. |
| `integrations/links/` | `IntegrationLinkViewSet` | GET/POST/PUT/PATCH | Auth + tenant + owner/tenant-admin integration permission. | Tenant integration registry; serializer keeps secret handling in owner surface. |
| `tables/` | `TableViewSet` | Router reads/writes | Auth + tenant + POS module; safe reads use `POS_ORDER_READ_ROLES`; table mutation is manager-only. | Outlet-scoped tables. |
| `orders/` | `OrderViewSet` | GET/POST/PATCH plus payment/line/promotion/refund/KDS actions | Auth + tenant + POS module. Reads use `POS_ORDER_READ_ROLES`; ordinary writes use `POS_SALES_OPERATOR_ROLES`; refund actions add manager approval; KDS action adds KDS permission. | POS order services, payments, refunds, line edits, promotion and folio operations. |
| `pos/shifts/` | `RegisterShiftViewSet` | GET, HEAD | Auth + tenant + POS module + `POS_ORDER_READ_ROLES`. Outlet queryset is membership-scoped. | Read-only register cash state for online/offline POS clients. Kitchen/cleaner roles are denied; this boundary was corrected in `f57853f0`. |
| `stock/balances/`, shelves, movements, transfers, counts | inventory viewsets | Read/write/action mix | Auth + tenant + inventory module + inventory capability. Accountant may read but `NotReadOnlyRole` blocks mutations; service-layer capability checks protect sensitive count/transfer transitions. | Membership outlet scope; stock services and transfer/count workflows. |
| `purchasing/suppliers/`, `purchasing/purchase-orders/` | purchasing viewsets | Router reads/writes + receive/payment/invoice/return/cost actions | Auth + tenant + purchasing module + action-specific purchasing capability. | PO receipt, supplier invoice/payment allocation, returns and cost confirmation services. |
| `lodging/room-types/`, rates, rooms, reservations, folios | lodging viewsets | Router reads/writes + check-in/out/folio actions | Auth + tenant + lodging module + lodging view role; unsafe methods use room/reservation/folio-specific management permissions. | Site-scoped PMS services, folio payments and reservation transitions. |
| `audit-events/` | `AuditEventViewSet` | GET, HEAD | Auth + tenant + manager audit-reader roles. | `visible_audit_events` applies manager/site/outlet evidence scope and payload redaction. |

### API-route regression contract

- Tenant context is resolved independently of business-role permissions; tests use neutral tenant settings for JWT context and dedicated permission-matrix tests for role denial.
- Finance, sales reports, audit, integrations, events, lodging, inventory and purchasing each have an explicit view/capability boundary instead of relying on tenant membership alone.
- Online order writes and offline POS writes share the same sales-operator role set.
- Register shift cash figures are protected by the same POS read roles as the staff Orders surface and by the POS module gate.
- Webhook/offline unexpected server errors are returned through the redacting API exception handler; mutation idempotency keys are not burned when durable processing fails.
- Router querysets remain tenant scoped and, where operational data is outlet/site specific, additionally use membership scope before user-supplied filters.


## `backend/apps/console/urls.py`

Console is split into a platform-neutral control plane and tenant-selected organization administration. Platform identity never derives from the selected tenant: tenant names appear only as explicit workspace records or the clearly labelled “Active workspace” being administered.

| Route names / paths | Owner and methods | Access boundary | Main dependencies / isolation |
| --- | --- | --- | --- |
| `console-index` · `/console/` | `ConsoleIndexView` · GET | Login required. Shows memberships to ordinary users; platform operators may list active workspaces. | No mutation. The selected tenant is presented as an administration context, not platform branding. |
| `console-select-tenant` · `select-tenant/` | `ConsoleSelectTenantView` · POST | Login required. Platform operators may select any active workspace; ordinary users must have an active membership in the target tenant. | Resets site/outlet session scope; validates same-host `next` before redirect. |
| `console-platform-tenants`, `console-platform-tenant-create`, `console-platform-tenant-edit`, `console-platform-tenant-control-plane` | Platform tenant list/create/update/control-plane · GET plus POST on form/action views | `PlatformOperatorRequiredMixin`: superuser or `is_platform_staff` only. | Tenant creation, subscriptions, entitlements, domains, billing, owner provisioning and access pause/restore. Control-plane PostgreSQL RLS scope is set only after platform-operator verification and to the requested tenant. |
| `console-platform-plans`, `console-platform-plan-create`, `console-platform-plan-edit` | Plan list/create/update · GET / POST | Platform operator only. | Global plan catalogue; tenant counts shown on list. |
| `console-org`, `console-org-setup`, `console-org-setup-step-state`, `console-org-practice-sale`, `console-org-catalog-import` | Org overview/setup/practice/import · GET / POST as declared | `ConsoleOrgAdminRequiredMixin`: active tenant context; owner/tenant-admin for ordinary users; platform operator may administer selected workspace. | Business-line gates prevent lodging/catalog/services pages when not enabled. Setup state, practice transaction and imports are tenant scoped. |
| `console-org-sites`, `console-org-site-create`, `console-org-site-edit`, `console-org-outlets`, `console-org-outlet-create`, `console-org-outlet-edit` | Branch/outlet list/forms · GET / POST | Org admin boundary. | Every queryset or nested lookup binds `tenant=request.tenant`; outlet form choices are restricted to configured business lines. |
| `console-org-room-types`, `console-org-room-type-create`, `console-org-room-type-edit`, `console-org-rooms`, `console-org-room-create`, `console-org-room-edit`, `console-org-room-rates`, `console-org-room-rate-create`, `console-org-room-rate-edit` | Lodging setup lists/forms · GET / POST | Org admin + lodging business-line gate. | Room type/room/rate querysets traverse the active tenant; submitted room types/sites are tenant constrained. |
| `console-org-modifier-groups`, create/edit, `console-org-modifier-options`, create/edit, `console-org-menu-categories`, create/edit | Menu structure lists/forms · GET / POST | Org admin + catalog business-line gate. | Tenant-scoped modifier/category querysets and nested scoped mixins. |
| `console-org-menu-items`, `console-org-menu-item-create`, `console-org-menu-item-edit`, `console-org-menu-item-photo` | Product catalogue, editor and phone-photo handoff · GET / POST | Org admin + catalog business-line gate. | Item reads/writes require active tenant; product registration is serialized per tenant; photo upload/status is tenant scoped and preserves desktop/phone race safety. |
| `console-org-menu-item-outlets`, create/edit/delete; `console-org-menu-item-recipe`, create/edit/delete | Product outlet and recipe children · GET / POST | `MenuItemScopedMixin` + org admin. | Parent item is first resolved with `tenant_id=request.tenant.id`; child querysets cannot cross tenant. |
| `console-org-service-offerings`, create/edit; `console-org-service-offering-options`, create/edit | Services and packages · GET / POST | Org admin + services business-line gate. | Service parent and package children are tenant scoped through `ServiceOfferingScopedMixin`. |

### Console-route regression contract

- `ConsoleTenantRequiredMixin` requires an authenticated user, selected active workspace and either an active membership or verified platform-operator scope.
- `ConsoleOrgAdminRequiredMixin` blocks non-admin worker roles and enforces business-line availability before organization pages execute.
- Nested site, outlet, room, catalogue, recipe, service and package routes resolve their parent inside the active tenant before touching children.
- Platform tenant and plan routes never rely on tenant membership; they require the independent platform-operator flag.
- Tests cover unrelated-workspace switching denial, server-role org denial, platform-route denial without the platform flag, platform-operator cross-workspace administration, and tenant-neutral organization branding.


## `backend/apps/staff/urls.py` and `backend/apps/staff/urls_workspace.py`

Staff uses `StaffTenantRequiredMixin` as the common deep-link boundary. When a view declares `staff_nav_capability`, the mixin computes the active tenant/outlet modules and role visibility server-side; hidden navigation alone is never treated as authorization.

| Route family / names | Owner and methods | Capability / access boundary | Main dependencies / isolation |
| --- | --- | --- | --- |
| `staff-login`, `staff-logout`, `staff-terminal`, `staff-terminal-lock`, `staff-pin-setup`, `staff-pending-approval` | Session/terminal views · GET/POST as declared | Login/PIN/terminal policies in the owner views. | Shared terminal session, PIN authentication and pending-workspace state. |
| `staff-dashboard`, `staff-help`, `staff-select-tenant`, setup-prompt dismiss/resume | Core staff shell · GET/POST | Authenticated user; tenant selection validates membership. | Dashboard visibility comes from effective modules and role-scoped navigation. |
| `staff-notifications`, `staff-notifications-status` | Notifications · GET, plus inbox POST actions | Active tenant membership; rows are always filtered to `recipient=request.tenant_membership`. | Private no-store inbox/status; read/refresh actions cannot target another recipient. |
| `staff-search` | Global search · GET/HEAD | Active tenant membership; each result group reuses nav visibility and domain permissions. | Tenant/outlet scoped search, rate limited JSON palette, private no-store response. |
| `staff-select-outlet`, `staff-retail-pos-entry`, `staff-orders`, `staff-order-quick-create`, `staff-order-detail`, `staff-order-print`, `staff-pos-shifts` | POS checkout/order views · GET/POST | `orders` capability, with action-specific cashier/manager approvals inside order detail. | Membership outlet scope, register shifts, payments/refunds, idempotency and canonical retail controller. |
| `staff-workstations`, create/edit/test/pair | Register hardware setup · GET/POST | `orders` capability; edit/test owners apply additional workstation checks. | Selected outlet/register pairing and browser/device approval. |
| `staff-tables`, `staff-table-create`, `staff-table-edit` | Table/floor setup · GET/POST | `tables` capability. | Tenant/outlet scoped tables; manager mutation checks in forms/views. |
| `staff-menu`; promotion list/detail/create/edit | Menu/promotions · GET/POST | `menu` or `promotions` capability respectively. | Tenant catalogue and promotion querysets. |
| `staff-sales` | Sales summary · GET | `sales` capability. | Date/outlet-bounded sales aggregation; membership outlet scope. |
| `staff-kds` | Kitchen queue · GET/POST | `kitchen` capability plus KDS action rules. | Outlet/station scoped KDS lines. |
| `staff-service-tv` | Service TV · GET | Custom read-only policy: active tenant membership, accessible outlet, enabled POS/kitchen module and hospitality business line. | Outlet-scoped orders/ready lines; guest mode strips staff performance/goal data. |
| `staff-retail-customer-display` | Second-screen customer display · GET | `orders` capability and session-protected order scope. | Read-only active sale display; no public order lookup. |
| Wholesale, pickup and delivery routes: `staff-wholesale-pricing`, `staff-retail-pickups`, `staff-deliveries`, `staff-delivery-packing-slip` | Retail operational views · GET/POST as declared | `orders` capability plus manager/customer/status rules inside each workflow. | Membership outlet scope; wholesale tier, pickup and delivery services. |
| Inventory routes: balances, intelligence, batches, movements, movement create/upload/template/errors, transfer/receipts, counts, shelves, scale labels, shelf labels | Inventory views · GET/POST | `inventory` capability plus capability-specific adjust/transfer/count approval checks. | Tenant and accessible-outlet scope. CSV template/error deep links now also carry the inventory capability in `78f940f6`; raw failed rows are not exposed to unrelated roles. |
| Purchasing routes: suppliers, supplier create/edit, POs list/create/detail, balances | Purchasing views · GET/POST | `purchasing` capability plus action-specific purchasing permissions. | Tenant/outlet scope; supplier invoices, payments, discrepancies, returns and costing. |
| Lodging routes: site selection, reservations, availability, tape chart, folios, rooms, housekeeping, maintenance, room types, night audit | Lodging views · GET/POST | `lodging` capability; cleaner exception is limited to `housekeeping_only`; mutations use reservation/folio/room permissions. | Site-scoped PMS data and business-date/night-audit services. |
| Event routes: spaces list/create/edit, bookings list/create/detail, calendar | Event views · GET/POST | `events` capability with event-manager checks for writes. | Site/event-space scope and booking services. |
| Finance routes: `staff-finance-entries`, create, category create | Finance views · GET/POST | `finance` capability; create/configuration additionally enforce finance write roles. | Site/cashbook scope and tenant currency. |
| Customer routes: list/create/detail | Customer views · GET/POST | Any of `orders`, `lodging`, `events` plus `can_manage_customers`/visible-customer rules. | Tenant and operational visibility scope; history/loyalty data remains customer-bound. |
| `staff-management`, `staff-management-shift`, `staff-management-source` | F5 management workspace · GET/POST / read-only evidence | Custom manager-role gate; policy changes additionally require workspace-settings permission and password-authenticated owner/admin context. | Scoped exception engine, case history, approvals, shift reconciliation and source evidence. |
| `staff-business-date` | Business date · GET/POST | `workspace` capability plus business-date management rules. | Tenant business calendar/night controls. |
| `staff-offline-queue` | Offline queue · GET | `offline_sync` capability. | Tenant/outlet-scoped offline operation state. |
| Workspace settings include: `staff-workspace-audit`, members/create/edit/deactivate/revoke-pin/bulk, invites/create/regenerate, branding, modules, integrations/create/edit, EFRIS/settings/evidence, owner reports | Settings/admin views · GET/POST | `workspace` capability. Mutating settings/team/integration routes require owner/tenant-admin; audit uses manager reader roles; owner reports require owner/admin password session. | All querysets bind active tenant; audit and EFRIS CSVs redact sensitive payloads; team objects are tenant scoped. |

### Staff-route regression contract

- `StaffTenantRequiredMixin` is a server-side capability gate for deep links; route visibility in templates is not authorization.
- Cleaner access is limited to the housekeeping-only lodging owner; ordinary lodging deep links remain denied.
- POS, inventory, purchasing, lodging, events, finance and workspace routes reuse the same capability names as navigation and effective module resolution.
- Manager-only Management has its own role gate and evidence scope rather than pretending to be another dashboard.
- Search and notifications intentionally lack a single nav capability because their service/query layers filter each result to the current membership’s authorized domains or recipient.
- Inventory CSV template/error exports were corrected to inherit the inventory capability so direct URLs cannot bypass the ledger/upload permission.
- Order/customer/display/report querysets remain tenant scoped and, where physical operations matter, are further restricted to accessible outlets/sites.
