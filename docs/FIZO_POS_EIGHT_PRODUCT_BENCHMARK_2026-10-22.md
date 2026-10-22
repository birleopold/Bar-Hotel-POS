# Fizo POS — Eight-product workflow benchmark (22 October 2026)

## Scope and evidence

Comparison of published vendor guidance, **not** logged-in trials or source audits of competing products. The Fizo observations come from the Bar-Hotel-POS repository as inspected on this date. The user's approved image remains the binding visual reference, and production appearance still requires authenticated browser inspection.

| Product | Vendor evidence | Strong workflow pattern | Fizo response |
| --- | --- | --- | --- |
| Square POS | https://squareup.com/help/us/en/article/8334-set-up-item-grid ; https://squareup.com/help/us/en/article/8634-customize-item-details-settings | Fast item grid, category shortcuts, direct add when no extra detail required | Existing tile form/quick add retained; missing configurable favourites |
| Shopify POS | https://changelog.shopify.com/posts/shopify-pos-version-11-0 | 2026 release simplified cart and contextual actions | Reworked basket rows and quick method controls; more simplification pending |
| Lightspeed Retail X | https://x-series-support.lightspeedhq.com/hc/en-us/articles/25534062778651-Using-the-Retail-POS-Sell-screen | Sell first, register status clear, quick keys and barcode scanning | Fizo POS link now resumes own active basket; no active basket gets dedicated New sale POST screen |
| Odoo POS 19 | https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/use.html | Persistent selector/cart/actions, separate current orders and register management; offline constrained | Split POS from Sales, retained shift checks; do not claim offline money processing |
| Loyverse | https://help.loyverse.com/help/sales ; https://help.loyverse.com/help/shift-management-loyverse-pos | Open tickets and auditable cash shifts | Existing server-led shift, hold and cash drawer logic retained |
| Erply | https://erply.com/point-of-sale/ | Save sale and retrieve recent transactions | Fizo active basket resume cards and separate receipt history |
| Toast | https://support.toasttab.com/en/article/New-POS-Experience-Ordering-Screens | Focused high-frequency actions and overflow for rare actions | Prefer contextual checkout; keep bar/restaurant menus independent |
| SumUp | https://www.sumup.com/en-gb/running-business/management/product-catalogue-for-maximum-checkout-efficiency/ | Arrange catalogue around cashier frequency and recognizable product photos | Visual product tiles retained; fast sorting/favourites not yet implemented |

## Existing data and authorization, no reckless schema edits

Fizo already uses per-tenant Orders, OrderLines, Payments, PosShifts, station selection, product categories and tracked inventory. The order detail DB queryset prefetches lines/menu items and payments; the retail checkout writes through existing authenticated POST handlers with stock checks, validation and idempotent payment-request keys. **No table migration is justified solely from visual competitor examples.** Before adding favourite tile/rank fields or indices, profile realistic per-tenant product volumes and index hit plans and provide a reversible migration with tests.

## Code changes in this benchmark batch

- `StaffRetailPosEntryView`: if shift open and user's own open basket exists, resume it; if none exists, render `staff/retail_pos_start.html` instead of returning to receipt history.
- `retail_pos_start.html`: explicit authenticated POST to `staff-order-quick-create`, clear register details, and links to history, shifts and workstations. GET does not create a basket or charge a payment.
- Styling `fizo-retail-sales.css` adds compact, responsive entry controls.
- Source/template regression tests added; not run in production.

## Remaining priorities (NOT shipped)

1. Authenticated screenshot comparison at reference desktop width and tablet, then close layout gaps.
2. Currency configuration: customer's screenshot showed USD though approved mockup showed UGX. Never hard-code UGX: review tenant currency setting and stored order currency before changing anything.
3. Show available product photos only from real inventory; provide useful icon fallback for products without images.
4. Profile product-search speed with 500 / 5000 / 20,000 items and index plans before database changes.
5. Consolidate duplicate scan and catalogue search fields only after testing scanner keyboard and modifier behaviour.
6. Improve hold / void / print actions with explicit confirmations where sensitive, but preserve authorization.
7. Inspect retry/idempotency, network failure and offline queue before promising disconnected sales.
8. Live cash/card/mobile-money receipt end-to-end test, never mark simulated payment as provider-confirmed.

Status: research done; checkout entry source-implemented; all browser and transaction acceptance still pending.
