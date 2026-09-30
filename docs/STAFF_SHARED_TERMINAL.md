# Shared staff terminal

One workstation can be used by multiple workers while each sale and action stays attributed to the correct account. The existing email and password sign-in remains available.

## First use

1. Each worker signs in with their own email and password and selects the correct workspace and section.
2. Open **Set PIN** in the staff sidebar. Enter the account password and choose a private 6 to 8 digit PIN. PINs are configured separately for each workspace membership.
3. When leaving the workstation, choose **Lock terminal** in the top bar or sidebar. After completing an order, **Done · lock terminal** is available beside the receipt controls. The current session ends immediately.
4. The next worker chooses their name on the locked screen and enters their PIN. The new session has that worker's permissions and the same section only if the worker is allowed there. A worker can always choose **Sign in with email and password** instead.

The locked screen only lists PIN-enabled active workers for the signed terminal's workspace and selected section. A shared terminal marker lasts up to 12 hours; after that, sign in with a password and lock the terminal again. **Sign out** ends the session and clears the marker. PIN-enabled sessions lock after two minutes without activity, both in the browser and on the server. Browser back navigation cannot reopen cached staff pages.

Five incorrect PIN attempts lock that worker's PIN for 15 minutes. The account password remains the recovery path; changing a PIN requires that password and ends older PIN sessions on their next request. PIN sessions cannot open the administration console or API routes. The terminal marker uses a signed, HTTP-only, same-site cookie and follows the deployment's secure-cookie setting. Audit events record PIN changes and terminal handoffs without recording PINs.

An owner or tenant admin can see PIN readiness in **Workspace → Members**, filter for workers who have not enrolled, and revoke another worker's PIN if a device or PIN may be compromised. Revocation ends existing PIN sessions on their next staff request. The worker can then sign in with their account password and set a new PIN. Managers do not see or choose workers' PINs.

## Deployment and verification

Deploy `accounts.0003_membership_staff_pin_failures_and_more` before enabling staff use. Existing workers can keep using their passwords until they choose a PIN. On a shared computer, verify lock, handoff between two roles, section restrictions, a failed PIN, browser back, and automatic idle lock. Run the full Django suite before release; a local test does not replace a real browser and production PostgreSQL check.
