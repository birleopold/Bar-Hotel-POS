# Supermarket checkout — reference-locked UI acceptance contract

**Design authority:** The three owner-provided screenshots in the ChatGPT Hotel and Bar project conversation dated 23 October 2026 (supermarket desktop grid / alternate desktop grid / POS touchscreen). These external chat images are not automatically available in the Git repository; compare the rendered screen against the original uploads during browser acceptance.

## Immutable direction
The retail/supermarket checkout **must visually match the references**. Do not replace it with a hospitality order screen, generic admin list, alternate POS theme, reimagined navigation, or gradient-heavy interpretation. Adapt only for functional accessibility, actual data, approved permissions and smaller screens. Screens with no customer are normal walk-in sales.

## Acceptance matrix
| Region | Must be visible | Reject if |
| --- | --- | --- |
| Left rail | POS, Sales, Products, Stock, Purchasing, Reports, Settings, Help; active POS state | Generic menu replaces cashier rail |
| Header | Brand and retail subtitle, wide scan/search, F3, register/shift and signed-in cashier | Identity missing, scanning buried |
| Categories | Horizontal large category tiles, clear green active tile | Small pill-only filters, vertical list |
| Product grid | 4 cards at medium desktop, 5 at wide desktop where space permits; photo, bold name, green price, full-width pale-green Add | Raw table or Add hidden in another form |
| Basket | Sticky right on desktop, green-tinted header, product thumbnails, unit prices, +/- controls and line amount | Basket below grid on desktop or missing empty state |
| Totals | Subtotal, discounts where applicable, total due in green, currency from order | Wrong currency or stale total |
| Payment | Strong full-width green pay action and immediately available Cash/Card/Mobile Money options | Payment method buried |
| Utilities | Hold, safe clear/void with reason, print where permitted | Destructive actions without confirmation or authorization |
| Responsive | Same identity and controls on tablet; single column only on narrow/mobile | Horizontal clipping or inaccessible pay |
| States | Empty, loading, invalid scanner code, no matching products, paid, held, locked terminal | Blank screen or deceptive successful status |

## Functional acceptance journeys
1. Owner configures UGX; cashier starts a **new** sale and sees UGX on every price, basket amount and payment control. Historical USD sales retain their original currency and show an explicit mismatch warning, never silent conversion.
2. An authorized cashier starts a shift, searches the full outlet catalogue, adds a pictured product from the grid, changes quantity, and sees the server-calculated basket amount.
3. F3 focuses the actual stock-validated scan field. Scan Enter adds through the existing authenticated `scan_add_line` endpoint. Unknown codes yield a meaningful validation response. Avoid double-submit.
4. Cash, card and mobile money method choices only select the existing payment form. **No UI shortcut posts money automatically.** Amount, tender and shift rules remain enforced server-side.
5. A cashier can hold/resume sale, void with a reason and print an authorized receipt. No hidden destructive GET actions.
6. An empty or restricted outlet retains the screen structure and a useful explanation. Customers are optional for supermarket purchases.

## Evidence required before marking complete
- Screenshots against all three user references at 1440x900 and 1920x1080, tablet ~1024, mobile ~390 width; inspect visual hierarchy, spacing, icons and images.
- Automated Django checks, migration drift and cashier-specific tests on the exact SHA.
- Real authenticated browser proof of basket, scanner, payment, return/hold/print and keyboard navigation.
- Confirm asset compilation/deployment and correct tenant/currency on production-like data.
- Never claim pixel parity solely from CSS being committed; record gaps and evidence.

## Current implementation
Styles: `backend/apps/staff/static/staff/retail-cashier.css` consolidates the earlier base and approved reference rules, preserving their original order; it is loaded by `order_detail_supermarket.html`.
Basket markup and tenant identity: `backend/apps/staff/templates/staff/order_detail.html`.
Server-side permissions, totals and posts: `backend/apps/staff/views_ops.py` and existing POS services.
**State:** implementation in progress; browser screenshot parity and production certification unverified.
