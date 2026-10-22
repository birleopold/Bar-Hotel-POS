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


## Follow-up implementation: discovery and cashier shortcuts

Implemented real catalogue search over product **name, SKU and barcode**, using already-rendered menu-item fields; added a clear-search control and improved the 'All items' category visual. Added contextual **Hold**, **Print** (only when receipt printing enabled) and **Sales** links alongside the basket. Hold uses the existing `hold_label` form, print uses existing `staff-order-print`, and Sales uses existing route; no new transaction or payment endpoint. Source regression checks updated. These changes do not yet implement database-backed favourites, product pagination or offline transactional changes. No server/browser tests performed in this batch.


## Popular-product shortcuts (2026-10-22)

Implemented `retail_quick_pick_ids` in `StaffOrderDetailView` from non-voided order lines belonging to paid, closed orders for the **current tenant and current outlet** during the prior 30 days. Ranked by sale-line occurrences; shortlist limited to existing visible/authorized catalogue items (max eight). The checkout now renders Quick picks buttons which click existing product tiles, invoking the normal validated add-line flow. No invented product imagery and no new database table. Low-sales shops show an explanatory empty state. Source-level regression checks added; **SQL profiling, tests, authenticated browser and transactions unverified**. A large-catalogue production load test should precede adding or changing database indexes.

## Product grid progressive reveal — 2026-10-22

The retail catalogue now initially shows the first **40 matching product cards**, with a visible count and "Show more products" button that increments by 40. Search and category changes reset the visible window; matching still searches **all items already rendered in the browser** and normal tile selection/add-to-basket handlers are preserved. This is **client-side progressive reveal only**, not server-side paging or virtualization: the queryset, form choice list, prefetch and initial HTML payload still load the full catalogue. For 5k-20k products, build an authenticated tenant/outlet-scoped backend search endpoint, paginate server results, query-index usage profiling and server validation tests before claiming true large-catalogue scalability. The test added is a source-level contract and remains unexecuted.

## Bounded server-side catalogue — 2026-10-22

Supermarket checkout now restricts the initial catalogue to 80 authorized items, with an outlet- and tenant-scoped server query (`catalogue_q`, max 80 chars) over name, SKU and barcode. An additional row detects when matches exceed the first 80; cashier is prompted to narrow search. On GET, the rendered `menu_item` dropdown is also restricted to those visible items, reducing the initial HTML option payload; POST form validation retains the full tenant/outlet-scoped queryset and existing stock/pricing handlers. Search remains available even when there are no matching categories. Independent `scan_add_line` is unaffected by the visual item limit. No migration introduced. This is a bounded search, **not offset pagination**, and the primary catalogue query can still need index tuning on very large datasets. Added regression source check; tests and browser flows are not executed yet.

## Checkout quick-create (QuickBooks-inspired), 2026-10-22

QuickBooks POS supports "ADD NEW" from receipt item selection when an item was omitted from inventory; the legacy QuickBooks POS guide warns of inventory-value discrepancies when no purchase cost exists. Sources:
- https://support.quickbooks.intuit.com/Support/store/pdfs/POS50GSG.pdf
- https://storage.googleapis.com/wzukusers/user-33607572/documents/5b435628df39aB6W7Gjp/QBPOS9UserGuide.pdf

Fizo implements `quick_create_product` directly in the open **supermarket/retail** order. Cashier enters item name, unit selling price, quantity and optional barcode. The view checks the current user's authorized outlet and edit capability, validates input, rejects existing barcodes, creates a tenant-scoped active MenuItem in the "Needs catalogue review" category with a generated QUICK SKU, **track_inventory=False**, then adds its line using existing `add_line_to_open_order` inside one transaction. `catalog.quick_product_created` audit tracks actor/user, product ID, order, outlet, price, quantity and review flag, with audit timestamp supplied by the audit model. No invented purchase cost, supplier, stock receipt or zero opening stock is recorded; manager must subsequently complete product cost/tax/stock settings. Existing order line price still goes through validated order services, and the quick item cannot be used as a way to bypass normal checkout payments. A pending review is represented by category + audit record (not a new database status column).

**Important:** This is only source committed, with source assertions and template compile checks created but not executed. Need real integration tests for permissions, repeated submissions, duplicate barcodes, atomic rollback, taxed items, stock reconciliation and production UI before marking accepted.

## Quick-product follow-up: review queue and outlet safety — 2026-10-22

A quick-created MenuItem now receives an explicit `MenuItemOutlet` link to the outlet at which the cashier created it. Under Fizo's catalogue service (unlinked MenuItems are available everywhere), this prevents accidental availability across all branches. The creation handler locks the current order, rechecks that it remains open and unpaid before creating the item, and checks same-name and same-barcode duplicates both before and within the transaction. This is not yet a global database unique constraint: concurrent creation for different orders can race, so collision tests and a proper idempotency key remain follow-ups.

Supermarket Products now surfaces a **Needs catalogue review** notice, a filter to quickly review QUICK-* records, and a **Complete product** link to the pre-existing console editor when the worker has workspace permissions. Review counts are limited to authorized outlets. Quick-product entry is positioned immediately below barcode scanning on the checkout screen; the submit button disables after valid submission to reduce double-clicks. No autonomous stock receipt or cost entry is invented.

Outstanding integration tests: quick-item creation/payment with two outlets, safe correction of cost and tax details, duplicate concurrent requests, disabled stock tracking, customer receipts, review-to-complete process and permissions. Source checks have been added but not run. No live deployment or browser screenshot acceptance was performed.

## Quick-product replay protection — 2026-10-22

The checkout renders a unique UUID `quick_product_request_key` with the quick-create form. The handler checks the existing tenant/order audit trail for an identical key before duplicate product checks and, under a row lock on the originating order, checks it again before creation. On success the audit event retains the key, order, operator, outlet, SKU and price context. A same-request retry on the same order is rejected without creating another catalogue item or basket line. The order row lock serializes duplicate requests for that particular sale. This does **not** guarantee database-wide uniqueness of product names or barcodes under concurrent separate orders; database unique constraints and actual concurrency tests remain necessary. No new migrations; source tests added, not executed.

## Cross-basket quick-create serialization — 2026-10-22

Fixed a weakness in the quick-item race mitigation: locking only the sale's `Order` row cannot coordinate **different** cashiers using separate orders. The handler now locks the shared tenant-specific "Needs catalogue review" `MenuCategory` row with `select_for_update()` before rechecking barcode/name and creating the product. This serializes quick-create operations for a tenant under PostgreSQL transaction semantics. The preflight duplicate check still gives a fast error and the in-transaction duplicate check remains authoritative. This does not serialize edits from the separate full-catalogue console, which currently does not acquire this lock. **Not yet fully race-safe across all product registration paths**, and concurrency tests on production-like PostgreSQL remain outstanding. Existing SKU and barcode values, historical sales and tenant currency are unchanged. Offline transaction recovery, 20k-item benchmarks, and currency default review remain outstanding, not implemented in this batch.

## Console + cashier shared registration guard — 2026-10-22

The management-console create/edit workflows now validate duplicate **tenant-scoped product names (case-insensitive)** and nonempty barcode values before saving, reporting inline form errors instead of silently allowing collisions. Console and cashier quick-add both acquire a row-level lock on the current `Tenant` inside an atomic transaction, so their final duplicate checks and writes serialize with one another under a transactional PostgreSQL backend. The cashier also retains its order lock and request-key replay check. No historic prices or receipts have been changed.

**Limitations:** Existing legacy duplicates are not removed; imports, API handlers, direct model writes and other paths may still bypass this lock; a database unique constraint has not yet been introduced because legacy duplicate data needs an audit/migration plan. This is also not an executed concurrency benchmark. Offline recovery, full catalogue stress tests, and tenant currency configuration remain open items. Source regression assertion committed but not executed.
