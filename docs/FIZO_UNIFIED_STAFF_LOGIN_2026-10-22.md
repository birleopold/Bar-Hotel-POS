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
