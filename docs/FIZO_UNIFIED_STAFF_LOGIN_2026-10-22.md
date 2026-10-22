# Fizo unified staff login — research and implementation

Date: 2026-10-22.

## Research grounding

- Shopify POS: https://help.shopify.com/en/manual/sell-in-person/shopify-pos/login and https://help.shopify.com/en/manual/sell-in-person/shopify-pos/manage-your-shopify-pos-pin — initial admin/device sign-in then staff-specific PIN for shared terminals, unique staff attribution and permission scoping.
- Toast: https://support.toasttab.com/en/article/Log-in-to-a-Toast-Product-or-Device — device authentication and staff POS passcodes are distinct, with switch-user flow and per-worker permissions.
- Square: https://squareup.com/help/us/en/article/8357-require-passcodes-at-point-of-sale — personal PINs provide individual attribution; shared team code should not replace that.
- Lightspeed: https://retail-support.lightspeedhq.com/hc/en-us/articles/229129648-Setting-login-credentials-and-access-settings — password-based external access, PIN-based lock/unlock on an established POS session.

## Fizo decision

Use two visible tabs with a **single design family**, preserving existing security:
1. Email & password: backend StaffLoginView and StaffLoginForm, tenant/domain and session validation unchanged.
2. Staff PIN: StaffTerminalView and StaffTerminalUnlockForm on established, tenant-scoped terminal only; 6–8 digits, worker selection, brute-force defenses and permissions unchanged.

Do not use a public PIN-only login in place of initial account or device trust. Do not reveal other businesses' staff. Keep user-selected workspace settings and white-label logo/name/accent. Password and PIN entry never appear in URLs. Form POST remains CSRF-protected.

## Implemented

- Responsive shared `staff/fizo-auth-2026.css`: dark emerald branding side panel on wide screens, compact single-column on <=900px, improved 460px handheld treatment, reduced heights for shallow terminals, and accessibility focus outlines.
- `staff/login.html`: coherent white-label staff login with prominent email/password path and PIN terminal tab.
- `staff/terminal.html`: same aesthetic, 6–8 digit PIN field, accessible touch number pad, clear/delete, supports physical keyboard.
- Tests verify both Django templates compile and the existing form bindings/CSRF/static asset references remain.

## Device acceptance checklist / not yet verified

- 1920x1080 / 2560x1440 landscape desktops; 1366x768 14-inch POS; 1024x768 register; 800x1280 tablet; 390x844 phone; 320px narrow phone; landscape handheld around 640x360; physical keypad.
- Confirm focus and tab order, no clipped keypad, minimum touch targets, zoom to 200%, screenreader field labels and errors, no unexpected virtual keyboard activation on keypad taps.
- Confirm white-label per-tenant domain isolation, PIN lockouts/rotation, open-shift staff switching, expired-device handling, session renewal and login redirects across restaurant, bar, hotel, retail, supermarket and central admin.
- No browser/production test run performed, nor does this change redesign console/platform-level sign-in forms if they are on separate routes.

Status: source implemented and committed only; no authenticated browser acceptance or live deployment.

## Admin-controlled password recovery — 2026-10-22 implementation

The previous `/api/v1/auth/password/reset/` endpoint immediately sent a reset token for any active User, with no tenant-membership revocation check. That is now replaced by an approval-request workflow:
1. Staff opens `/password-reset/` from the password login; submits work email. It returns a generic message. A per-email/IP cooldown reduces repeated submissions; existing, eligible active accounts receive one pending `PasswordRecoveryRequest`. No password or token is emailed yet.
2. A platform operator reviews the pending account request in Django platform administration (`/admin/` → Password Recovery Requests) and selects **Approve and email recovery link** or **Deny**. The system checks active User/tenant membership; disabled or dismissed-only staff cannot be approved.
3. Approval requires a configured HTTPS `PASSWORD_RESET_URL_TEMPLATE` ending in `/password-reset/confirm/` with `uid` and `token` placeholders. A fresh Django password reset token is emailed to the account owner only after the approved record commits. The server stores only SHA-256 of token (not token itself), an approval actor, and 30-minute expiry.
4. Web and API confirmation share the same checks: active user, at least one active tenant membership if memberships exist, approved unexpired matching token digest, token validity, and Django password strength rules. A successful use changes password, invalidates the token and marks the request used.
5. Historical sessions become invalid on subsequent Django session verification when password hash changes. Independently, **staff dismissal must deactivate membership and terminate device sessions** rather than rely on password recovery approval alone.

Important limitations and required deployment verification:
- New database migration `accounts.0006_passwordrecoveryrequest` **must be applied** before deploying routes; set a valid HTTPS reset URL and working email delivery.
- Platform admins need real notification of new pending requests (currently admin list view; no push notification).
- No manager-specific approval inside each tenant is implemented. A tenant manager does not automatically receive platform admin credentials; owners should report dismissed worker accounts via existing management process.
- PIN reset remains password-authenticated via existing `staff-pin-setup` and terminal security.
- Account-wide User passwords can span multiple tenants; disable individual Membership access independently.
- Backend and UI security tests are added/adjusted but not executed in this session. Do not use production until expiry, revoked-membership, mail dispatch, account enumeration, session invalidation, and approval authorization are integration-tested.
