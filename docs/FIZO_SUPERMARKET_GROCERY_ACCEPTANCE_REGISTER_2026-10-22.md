# Fizo Supermarket and Grocery — Screen-by-Screen Acceptance Register

This register is specific to supermarket and grocery workflows and is a supplement to the full 628-pattern Django runtime inventory. Routes/shared pages below must be tested using an authorized supermarket tenant and cashier, supervisor, storekeeper and owner roles. Dynamic conditions can change the selected template.

**Rule:** SOURCE IMPLEMENTED is NOT browser verified. No screen is complete without actual user-flow, access-control, responsive browser and production evidence.

| # | Page or workflow | Route name or route family | Primary template or UI | Source redesign | Acceptance |
|---:|---|---|---|---|---|
| 1 | Owner dashboard / setup / activity | `staff-dashboard` | `staff/dashboard.html` | Fizo v2 source | UNVERIFIED |
| 2 | Sales POS landing, new sale, held sale, history | `staff-orders`, `staff-order-quick-create` | `staff/orders_list.html` | Independent Fizo cashier sales landing source committed | UNVERIFIED |
| 3 | Active cashier basket and payment | `staff-order-detail` | `staff/order_detail_supermarket.html`, base `order_detail.html` | Fizo catalogue/basket source | UNVERIFIED |
| 4 | Barcode scan and shelf product selection | Order POST action | Checkout template and JS | Fizo source | UNVERIFIED |
| 5 | Receipt view / printing | Order print routes | `staff/order_print.html` | Requires individual design | UNVERIFIED |
| 6 | Second-screen customer display | Customer display route | `staff/pos/customer_display.html` | Requires individual design | UNVERIFIED |
| 7 | Product catalogue (staff) | `staff-menu` | `staff/menu_list.html` | Fizo retail table source | UNVERIFIED |
| 8 | Product/category administration | `console-org-menu-*` | `console/org/menu_item_*.html`, `menu_category_*.html` | Not audited | UNVERIFIED |
| 9 | Product import / bulk prices | `console-org-catalog-import` | `console/org/catalog_import.html` | Not audited | UNVERIFIED |
| 10 | Stock overview, lots and transactions | Inventory routes | `staff/inventory/balances.html`, `batches.html`, `movements.html` | Balances page restructured in Fizo; batches and movements still outstanding | UNVERIFIED |
| 11 | Stock counts, transfers and receipts | Inventory routes | `staff/inventory/count*.html`, `transfer*.html` | Not audited | UNVERIFIED |
| 12 | Shelf locations and scale labels | Inventory routes | `staff/inventory/shelves.html`, `scale_labels.html` | Not audited | UNVERIFIED |
| 13 | Stock intelligence / low stock | Inventory intelligence route | `staff/inventory/intelligence.html` | Not audited | UNVERIFIED |
| 14 | Purchasing, supplier management, delivery | Purchasing routes | `staff/purchasing/*.html` | Not audited | UNVERIFIED |
| 15 | Supplier balances | Purchasing balance route | `staff/purchasing/supplier_balances.html` | Not audited | UNVERIFIED |
| 16 | Wholesale price tiers | `staff-wholesale-pricing` | `staff/pos/wholesale_pricing.html` | Not audited | UNVERIFIED |
| 17 | Paid customer pickup | `staff-retail-pickups` | `staff/pos/pickups.html` | Not audited | UNVERIFIED |
| 18 | Cashier shifts, till pairing, terminal | Staff workstations and shifts | `staff/pos_shifts.html`, `workstations.html`, `terminal.html` and related templates | Not audited | UNVERIFIED |
| 19 | Offline queue/sync | Offline staff and API routes | `staff/pos/offline_queue.html` + API | Not audited | UNVERIFIED |
| 20 | Customer directory, loyalty context | Staff customers routes | `staff/customers/*.html` | Not audited | UNVERIFIED |
| 21 | Sales reports and finance | Sales and finance staff routes | `staff/sales_summary.html`, `staff/finance/*.html` | Not audited | UNVERIFIED |
| 22 | Returns and refunds | Existing order detail POST actions | Retail checkout/receipt | Source actions preserved | UNVERIFIED |
| 23 | Promotions and discounts | Staff promotions routes | `staff/promotions_list.html`, `promotion_*.html` | Not audited | UNVERIFIED |
| 24 | Staff roles, staff PIN, settings and brand | Shared staff settings and console | `staff/settings/*.html`, `staff/pin_setup.html` | Not audited | UNVERIFIED |
| 25 | Initial business/site/outlet setup | `console-org-setup` and related console routes | `console/org/*.html` | Partial Fizo source | UNVERIFIED |

Also audit *all shared includes and shells*, staff terminal lockdown, partial receipt/print views, platform permission checks and API actions, not just page templates. The runtime CSV is authoritative for exact route patterns; this table is a workflow-oriented design worklist.

## Visual acceptance standard

Use four reference images supplied by the user: unified suite, owner supermarket dashboard, five-column cashier catalogue + sticky basket, and compact four-column cashier catalogue variant. Preserve Fizo white/green, legible navy typography, dense-but-touchable product grids, clearly separated basket, prominent one-action checkout, and business-specific navigation. Never populate examples with invented sales/product values.

## Evidence required to close a row

1. Real route, assigned tenant/site, tested roles and permission denials.
2. Django template compilation and automated workflows.
3. Authenticated browser screenshot at desktop/tablet/phone, matched to the corresponding reference.
4. Product/order/stock/payment interactions end-to-end with real backend validations.
5. Static deployment checked, no orphan legacy CSS, deploy revision and screenshot recorded.

**No rows currently have sufficient acceptance evidence for DONE.**


## Batch: Stock balances page

Implemented dedicated `fizo-stock.css` and rebuilt `staff/inventory/balances.html` using product, outlet, quantity and reorder data from the existing view. Preserved search, low-stock filtering, pagination, and authorization gates on stock actions. Fixed duplicate low-stock query parameters in paging. Source-level template compilation and route tests were added but **have not yet been run**. Desktop/tablet/mobile browser testing and stock workflow acceptance are still outstanding.


## Cashier sales landing redesign (2026-10-22)

`staff/orders_list.html` now routes only `show_supermarket_lane` to a fresh included DOM `staff/includes/fizo_retail_sales_landing.html` with `fizo-retail-sales.css`. Restaurant and bar retain their original ordering branch. The page retains register-shift gate, quick-create POST with CSRF, held baskets, active lanes, receipt status filtering, search, pagination and original order detail links. No customer is required for a walk-in checkout. New regression tests added but not executed; browser acceptance remains **UNVERIFIED**.


## Inventory ledger, batches and receive/adjustment form (2026-10-22)

Three more *individual* pages updated: `staff/inventory/movements.html`, `staff/inventory/batches.html`, and `staff/inventory/movement_form.html`. Each now uses a dedicated Fizo inventory workspace CSS and heading, with new table/panel classes rather than the rejected page hero. Existing queryset references, batch status/search, FEFO restrictions, receiving and labeling form actions, CSV export, permissions and CSRF tokens were preserved. Django parsing tests were added but not run. These rows are **SOURCE IMPLEMENTED, BROWSER UNVERIFIED**. 
