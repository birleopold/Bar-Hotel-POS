# Supermarket & grocery POS — cashier-first UX benchmark (October 2026)

## Scope and evidence
Reviewed publicly documented checkout flows/screens for seven systems:
1. Square Retail: https://squareup.com/help/us/en/article/8334-set-up-item-grid — editable frequently used item grid.
2. Shopify POS: https://help.shopify.com/en/manual/sell-in-person/getting-started/smart-grid — configurable location-based smart grid.
3. Loyverse: https://help.loyverse.com/help/how-to-arrange-sale-screen-loyverse and https://help.loyverse.com/help/make-sales — ticket, browse/list, cash/change and Charge.
4. Lightspeed X-Series: https://x-series-support.lightspeedhq.com/hc/en-us/articles/25534062778651-Using-the-Retail-POS-Sell-screen — scanner and search from Sell screen, register handling.
5. Odoo: https://www.odoo.com/app/point-of-sale-features — browser-based checkout, product search and mixed payment capabilities.
6. ERPLY: https://wiki.erply.com/article/779-standard-pos-views — retail barcode mode versus quickserve touchscreen mode.
7. Oliver POS: https://oliverpos.com/en-gb/product/ — parked sales, accessible payment controls and split tender.

These are published product walkthroughs/screens, not credentials-based hands-on use of private demo accounts.

## Decision
Retail/supermarket is a distinct workflow. No tables, compulsory named shopper, room selection, food prep or waiter state.

Primary lane: New sale → Scan/find item → Review basket → Pay → Receipt → Next sale.
The current server-side sales, payment and inventory services remain authoritative. Do not bypass transaction/stock validation to achieve faster UI.

## Prioritized UX plan
- **P0: Checkout launch / language (started).** Expose Start checkout directly, clearly communicate register opening, remove jargon from barcode and cash panels. Preserve hold/resume, refunds and shift controls as secondary tasks.
- **P1: Cashier checkout layout (pending).** Desktop/tablet: scanner/search and item list left, persistent basket/totals/payment right. Mobile: sticky basket-total/pay footer; product list above. Keep focus in scanner after successful add. Single primary action at each stage.
- **P1: Search and barcode (pending).** Search by name, SKU, barcode or PLU; fast exact-match scan; clear errors for unknown products; duplicate scans add quantity; support weighted items with correct decimal precision.
- **P1: Payment (pending).** Pay button always shows outstanding amount and supported tender methods. Cash screen: amount due, amount tendered, change due. Do not mark paid before backend confirmation; prevent double submission.
- **P1: Receipt (pending).** Clear success state, receipt/print/reprint and Next shopper. Do not require customer account.
- **P2: Common grocery tasks (pending).** Product tiles/favorites for unbarcoded produce, held baskets, returns, discounts with manager permissions, shift reconciliation, stock visibility and low stock alerts.
- **P2: Non-technical usability (pending).** Larger targets; plain-language labels; clear failures and next steps; keyboard, mouse, touch and barcode scanner; WCAG focus and contrast; mobile, 10-inch tablet and desktop tests.
- **P3: Role-focused navigation (pending).** Cashier only sees Sales/Checkout, Receipts, Shift and authorized Returns; manager sees inventory, purchasing, reports, users. No bar/hotel affordances in supermarket.
- **Verification required.** Automated checkout journeys plus actual browser tests on narrow mobile, tablet, desktop; keyboard scanner; shift closed/open; refunds, offline conflicts, retry/double-payment and receipt printer.

## Change log
- Sales landing page: prominent Start checkout/Open register action for supermarket and retail.
- Checkout scan/cash headings and help text simplified without changing backend money movement.
- Full redesign has NOT been implemented yet.
