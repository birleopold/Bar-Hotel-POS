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
