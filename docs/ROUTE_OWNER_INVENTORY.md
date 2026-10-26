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
