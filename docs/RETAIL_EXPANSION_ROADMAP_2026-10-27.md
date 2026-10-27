# Retail expansion roadmap — QuickBooks-depth benchmark

**Created:** 27 October 2026  
**Scope:** retail/supermarket/wholesale capabilities that extend the existing Bar–Hotel–Retail suite.  
**Authority:** this is an execution layer over the existing 34-phase roadmap and supermarket checklist. It does not replace either document.

## Rules

- Extend existing services, screens and ledgers. Do not create parallel checkout, stock, customer, purchasing or finance engines.
- Every workstream is delivered **backend → service/domain rules → UI/navigation → permissions/audit → tests → exact-head CI**.
- Preserve current fast supermarket basket behavior, held baskets, partial/mixed tender, stock posting, refunds, workstation flow and business-line isolation.
- Retail-only features must not leak into hotel/bar/restaurant workspaces unless explicitly shared.
- Provider payment integrations are deferred. Card/mobile-money/provider-specific APIs, terminal SDKs and settlement integrations are out of scope for this roadmap until selected by the owner.
- Existing generic payment records remain usable for cash/manual methods and future provider adapters.
- Do not implement a partial accounting system and call it full accounting. Build an operational accounting bridge and export/integration layer first; a true general ledger remains a separate strategic decision.

## Parallel workstream RX — Migration & platform interoperability

**Goal:** make it straightforward for a tenant to move product/catalogue data into or out of this POS without bypassing our canonical product, package, stock, tax, pricing or tenant rules.

**Execution rule:** RX is a standing parallel workstream. Whenever R1–R7 adds a portable business entity (products, packages, customers, suppliers, price books, stock balances, POs, etc.), add/import/export compatibility at the same time where practical instead of returning later.

### RX.1 Canonical migration boundary
- Keep one stable neutral migration schema owned by this project.
- External-platform adapters translate into that schema; they do not write directly to stock or checkout tables.
- Every import supports preview, row validation, all-or-nothing commit where practical, audit evidence and tenant scoping.
- Never silently overwrite existing SKUs/barcodes/serial identities; require explicit update workflows.
- Preserve source identifiers in alternate/reference fields where useful for later reconciliation.

### RX.2 Product/catalogue adapters — priority
- Generic column-mapping importer for arbitrary CSV exports.
- Shopify product CSV adapter, including variant rows where representable.
- Square item-library CSV adapter.
- QuickBooks Online products/services adapter.
- WooCommerce product CSV adapter.
- Keep adapter definitions versioned because vendor export formats change.
- Unsupported vendor-specific fields must be reported as ignored/unmapped before import, never silently dropped.

### RX.3 Outbound compatibility
- Neutral full catalogue migration export.
- Platform-oriented export profiles where the target format is stable and supportable.
- Export products, concrete variants, package/unit relationships, barcodes/SKUs, brand/model/reference, prices, tax metadata and active state where the target supports them.
- Do not export live stock quantities as product metadata; stock migration uses a separate controlled opening-stock workflow.
- No claim that a target platform will accept every field until verified against that platform's current importer.

### RX.4 Later entities
- Customers and customer groups/price levels.
- Suppliers and supplier-specific product/package codes.
- Opening stock by branch/outlet, with explicit as-of date and no historical movement fabrication.
- Purchase orders/open receivables only through dedicated migration workflows.
- Accounting-ready exports/adapters under R7.

### RX.5 Compatibility acceptance
- Round-trip tests for our neutral format.
- Golden-file tests for supported vendor formats.
- Duplicate/collision, encoding, formula-injection and oversized-file tests.
- Migration report: imported, skipped, unmapped, rejected and warnings.
- Exact vendor/version/date recorded in adapter metadata.

**Current official-format notes (27 October 2026):** Shopify currently requires UTF-8 product CSVs; Square's item-library CSV requires Item Name, Variation Name, Description and SKU (plus enabled-location columns for multi-location libraries); QuickBooks Online supports mapped CSV/Excel product/service imports with up to 1,000 rows per import and currently notes that product variants are no longer supported as of 1 June 2026. Vendor schemas must therefore remain adapter/version metadata rather than hard-coded assumptions across the product domain.

## Workstream R1 — Merchandise master and product structure

**Goal:** make one catalog capable of handling simple groceries, fashion variants, electronics, wholesale packs and assembled/bundled products without duplicating stock logic.

**Maps to:** phases 07, 08, 15, 25, 27; SM-02, SM-12, SM-14, SM-15, SM-19, SM-26, SM-31, SM-32.

### R1.1 Product families and variants
- Parent product / variant family.
- Variant dimensions such as size, colour, material and tenant-defined option names.
- Generate or manually assign SKU/barcode per concrete variant.
- Variant-specific image, active state, price, cost, reorder level and stock tracking.
- Matrix UI for fast creation/editing.
- Search and scan always resolve to the concrete sellable variant.
- Existing simple products remain valid without forced migration.

### R1.2 Packaging and units
- Base stock unit plus sell/purchase packages.
- Piece, pack, case/carton and configurable conversion factors.
- Barcode per package size.
- Purchase in cartons, sell in pieces without duplicate inventory ledgers.
- Cost allocation into base units.
- Decimal/weight units remain supported.
- Guard against non-integral package rules where product policy requires whole units.

### R1.3 Assemblies, kits and groups
- Retail assembly recipe/BOM distinct from restaurant recipes but using shared component concepts where practical.
- Build/unbuild assembly transactions with audited stock movements.
- Non-stock group/bundle that expands at sale time without pre-building stock.
- Bundle price and component stock checks.
- No double consumption with restaurant recipe logic.

### R1.4 Serialized products
- Optional serial/IMEI tracking by SKU.
- Receive serials, hold/quarantine, sell one serial once, return original serial, warranty lookup.
- Serial state/history screen.
- Bulk supermarket products remain unaffected.

### R1.5 Merchandise metadata and labels
- Tenant-defined product custom fields.
- Brand/model/reference/MSRP fields.
- Multiple alternate lookup codes.
- Label templates: shelf, product, markdown, receiving.
- Label queue for newly received or price-changed products.
- Existing Code 128/weighted-label work reused.

**UI surfaces:** Catalog list, product editor, variant matrix, package/UoM editor, assemblies, serial registry, label queue.

## R1 implementation checkpoint — 27 October 2026

Implemented in source. Exact-head software checkpoint is recorded below; deployed browser/hardware certification remains separate:
- Product families with tenant scope and PostgreSQL RLS.
- Variant matrix preview/generation for up to three dimensions and 120 combinations per batch; generated rows remain normal sellable `MenuItem` SKUs.
- Product packages with base-unit conversion, package barcode/code, sell/purchase flags and optional exactly representable package price.
- Symmetric barcode/SKU/package-code collision guards.
- Cashier scan resolution and catalogue search by package barcode/code; package scans convert into base stock quantity through the existing basket service.
- Purchase-order package snapshots: package name, units per package and ordered package count are frozen on the PO line while financial/stock quantities remain base units.
- Staff PO creation and receiving UI for package counts; partial receipt converts packages to base stock and records packages received.
- Service-level rejection of fractional package receipt counts.
- Retail-only UI isolation for family/package tools.
- Retail assembly BOM configuration under each tracked product, separate from hospitality recipes.
- Staff Inventory Build/Unbuild operation with outlet scope, atomic component/finished-stock posting, run history and linked stock movements.
- Assembly operations block any involved item with batch/expiry history until lot-aware assembly output allocation is implemented.
- Non-stock retail quick-sale groups with tenant/RLS-scoped component rows, atomic expansion into ordinary basket lines, scan-code fallback and lossless async quick-group buttons.
- Serialized/IMEI product configuration, exact-unit receipt custody, cashier reservation/fast IMEI scan, payment settlement, warranty-from-sale, returns/quarantine, exact transfers and trace register with RLS.
- Standard merchandise identity fields (brand, model/style, reference and MSRP), tenant-defined typed custom fields and active alternate supplier/manufacturer/internal lookup codes.
- Alternate-code scanner/catalogue search integration with a shared collision-safe product/package/group/PLU/serial namespace.
- Product label queue for new products, price changes, imports and receiving; existing Shelf labels UI now filters pending work, prints current outlet prices, records printed completion, supports manual requests, audited dismissal and recent completion history.
- Four current-PDF merchandise label modes on the same queue/workflow: shelf/price, product identity, markdown and receiving.
- Package-aware catalogue CSV workflow separated from simple-product import: sample/export, preview, create-only atomic import by concrete product SKU, scanner-namespace validation, exactly representable package pricing and stock-neutral writes.

Still R1 work:
- richer variant option editing after generation;
- supplier-specific package codes/cost relationships belong primarily to R4 product/vendor sourcing rather than the generic package master;
- combined lot+serial allocation where a business genuinely needs both trace dimensions on one product;
- richer thermal/physical label layouts and printer/media/scanner read-back certification;
- deployed desktop/tablet/mobile browser acceptance and production RLS-role certification.

Exact-head software evidence:
- `8b4788aadc4be3e75db9e77719179f36bf0f208b` — 1,253 tests passed, 7 skipped, 1,317 subtests; PostgreSQL integration green after metadata/group/serial/label-queue recovery.
- `cb4cff105e9c7774f9605f828a0f91e0b540e7fb` — 1,262 tests passed, 7 skipped, 1,317 subtests; Django checks, migration drift and PostgreSQL integration green with package CSV import/export and package identity guards.
- These are software checkpoints only; they do not claim deployed browser/device/printer certification.

## R2 implementation checkpoint — 27 October 2026

Implemented in source, pending exact-head software/browser certification:
- Fixed-amount and percentage offers continue to use the existing order promotion engine; no second checkout discount path was introduced.
- Offers can target one concrete product, product family, category, case-insensitive brand, or the whole basket.
- Targeted offers calculate their discount basis only from matching basket lines and remain removable before payment starts.
- Apply/remove promotion actions are asynchronous at checkout and are frozen once tendering begins.
- Unsupported stacking is blocked against wholesale pricing, customer price-book rules and manual line discounts.
- Minimum order subtotal and minimum qualifying target quantity are supported.
- Optional coupon codes are tenant-unique and hidden from the normal offer dropdown; cashiers must enter the code explicitly.
- Optional global and per-identified-customer redemption limits count fully paid orders, so apply/remove/reapply clicks do not consume redemptions.
- Staff management and API serializers expose the same target, coupon, quantity and redemption controls.
- X-for-fixed-amount quantity deals run through the same promotion engine: complete whole-unit sets only, product/family/category/brand target, optional per-order set cap, live basket recalculation, API/staff controls and a fail-closed guard when the configured deal would not reduce the qualifying price.
- Buy-X-Get-Y now supports a distinct reward product/family/category/brand while preserving same-pool BOGO when no reward target is set. The reward must already be in the basket, reward/qualifying pools must be non-overlapping in this first safe implementation, the cheapest eligible reward units are discounted, and live basket mutations recalculate the saving.
- Mix-and-match fixed-price deals are supported within one merchandise pool (for example any 3 items in a category/brand/family for one fixed amount) through X-for-fixed-amount; arbitrary multi-pool mix-and-match remains deferred.
- Promotion governance now includes a consolidated Offers performance view over selectable 7/30/90/365-day windows using fully paid orders only: uses, gross sales, discount value, net sales and identified-customer count. Offer detail exposes the same paid-order metrics without creating a second reporting engine.
- Recent audited base-price, outlet-price and variant-price changes are surfaced in the Offers area from the existing audit ledger, preserving before/after, outlet, operator and timestamp evidence.
- Safe physical markdowns are synchronized into the existing merchandise label queue. Only unconditional standard offers with a truthful per-item price are auto-queued; coupon/minimum-basket/minimum-quantity and ambiguous multi-item fixed-amount deals are deliberately excluded. The markdown label prints the promotional price snapshot and regular price, and printing it completes only the markdown queue task.
- Promotion edits/deactivation reconcile and dismiss stale promotion-owned markdown tasks before creating replacements, preventing obsolete promotional shelf prices from remaining printable.
- Retail pricing precedence is now centralized in one service and reused by offer selection, offer application, manual line discounts, wholesale pricing and checkout presentation. The current safe contract keeps order promotions exclusive from wholesale, customer price-book and manual line-discount pricing, while manager-approved wholesale can replace a customer price-book rate on the same line.
- The cashier now sees the active pricing layer and the reason an offer or wholesale action is blocked instead of seeing a control that the backend will later reject.
- Promotion performance can now be filtered to an accessible outlet and exported as CSV with offer, type, target, paid uses, gross sales, discount value, net sales, identified customers, currency, time window and outlet scope.
- Recurring offer schedules now support optional ISO weekdays plus business-local start/end times on top of the existing date range. Checkout selection and apply-time validation use the tenant's configured timezone; overnight windows fail closed and should be split into two simple schedules.
- Recurring day/time promotions are deliberately excluded from automatic plain markdown shelf labels because a static “Now” price would be misleading outside the active window; date-range-only unconditional markdowns continue to use the existing queue.

Still R2 work:
- arbitrary multi-pool mix-and-match mechanics beyond one product/family/category/brand pool;
- group/bundle promotional pricing;
- an explicit multi-offer stacking/precedence contract if simultaneous offers are later allowed;
- margin-floor threshold configuration, trusted-cost enforcement and manager reconciliation for incomplete positive legacy stock are implemented; remaining work is richer profitability reporting and controlled correction of already-trusted accounting cost if ever required;
- exact-head CI and deployed browser/till acceptance for this promotion checkpoint.

## Workstream R2 — Pricing, promotions and merchandising

**Goal:** centralize all non-base-price behavior in one pricing engine instead of scattered checkout conditions.

**Maps to:** phases 06, 18, 20, 21, 22, 27, 32; SM-05, SM-20, SM-22, SM-25, SM-30, SM-31, SM-35.

### R2.1 Price books and customer price levels
- Base, retail, wholesale, VIP, employee and tenant-defined price books.
- Outlet applicability.
- Effective start/end dates.
- Product/category/variant rules.
- Customer or customer-group assignment.
- Quantity tiers and pack/case prices.
- Clear precedence and immutable applied-price snapshot on sale lines.

### R2.2 Promotions
- Percentage/fixed discounts.
- Buy X get Y.
- X for fixed amount.
- Mix-and-match.
- Category/brand promotions.
- Bundle discounts.
- Scheduled markdowns.
- Coupon codes and usage limits.
- Minimum basket/quantity conditions.
- Margin floor and manager override where configured.
- Explicit stacking/precedence rules.

### R2.3 Promotion governance
- Manager approval for protected discounts/overrides.
- Before/after audit.
- Promotion performance report.
- Price-change history.
- Markdown label queue.

**UI surfaces:** Price books, promotion builder, coupon manager, price history, markdown queue, promotion report.

## Workstream R3 — Customer commerce, credit and order lifecycle

**Goal:** support customer transactions that are not immediate anonymous cash sales.

**Maps to:** phases 05, 06, 20, 21, 22, 32; SM-06, SM-22, SM-23, SM-24, SM-25, SM-30.

### R3.1 Retail customer accounts / A/R
- Credit account opt-in per customer.
- Credit limit, available credit, account status and hold.
- Charge-on-account sale.
- Terms: due on receipt / Net N days.
- Customer invoices and immutable account ledger.
- Receive payment on account.
- Allocate payment to invoices.
- Customer credit/overpayment.
- A/R ageing 0–30 / 31–60 / 61–90 / 90+.
- Statements.
- Manager approval for limit override, write-off and credit adjustment.
- No dependency on hotel folios.

### R3.2 Quotes, sales orders and special orders
- Quote → accepted sales order → fulfillment → sale/invoice.
- Reserve or commit stock without posting sale/payment.
- Special-order unavailable item from supplier.
- Backorder and partial fulfillment.
- Pick list.
- Convert receiving availability into fulfillment notification.

### R3.3 Layaway
- Reserved inventory.
- Deposit schedule.
- Remaining balance.
- Expiry/cancellation.
- Controlled stock release.
- Refund/cancellation policy.
- Final collection converts to completed sale once payment policy is satisfied.
- Must not reuse paid-pickup as fake layaway.

### R3.4 Exchanges and store credit
- Original receipt lookup.
- Return selected original lines.
- Add replacement items in same controlled transaction.
- Collect/refund the net difference.
- Preserve tax/discount allocation.
- Optional refund to store-credit ledger.
- Store credit has immutable balance/history.

### R3.5 Gift cards/vouchers
- Issue, activate, redeem partially, reload if enabled, expire if policy allows.
- Barcode/QR/code lookup.
- Liability balance.
- Multi-branch redemption within tenant.
- Replacement/revocation audit.
- No external payment-provider API required.

### R3.6 Loyalty and segmentation
- Tier rules.
- Birthday/visit/spend offers.
- Coupons.
- Customer segments: top spenders, dormant, category buyers, frequent visitors.
- Consent/preferences.
- Reward balance on receipt/customer display where enabled.

**UI surfaces:** Customer account tab, credit account dashboard, statements, quotes, sales orders, layaway, exchange screen, gift/store credit, loyalty tiers/segments.

## R4 implementation checkpoint — 27 October 2026

Implemented in source, pending exact-head certification:
- Outlet stock balances now carry an optional weighted-average unit cost plus an explicit `cost_basis_complete` trust flag. The average is only authoritative when every on-hand unit has known cost evidence.
- Confirmed purchase receipts snapshot the PO unit cost used for that physical receipt and update the outlet weighted average transactionally after stock is posted.
- Receiving costed stock into existing legacy/uncosted on-hand inventory deliberately leaves the balance cost-incomplete instead of inventing a blended average.
- Direct tracked retail sale lines snapshot the authoritative outlet unit cost when inventory posts, so later purchase-price changes do not rewrite historical sale cost evidence.
- Immediate and staged stock transfers capture the source outlet cost at dispatch and blend it into the destination only when the source basis is complete; uncosted transfers remain untrusted at destination.
- Manual stock increases, upward physical-count corrections and assembly-created stock invalidate cost trust unless a dedicated known-cost workflow supplies evidence.
- Legitimate retail and serialized restocks reuse the original sale-line cost snapshot when it was authoritative; historically uncosted returns remain incomplete.
- The existing Stock balances screen now shows average cost, trusted inventory value and an explicit `Cost incomplete` state instead of hiding cost coverage in the database.
- This is weighted-average cost by outlet. Trusted retail assembly build cost roll-up is implemented; historical-cost reconstruction for unbuild remains deferred.
- Receipt-level landed-cost allocation is implemented for shipping/freight and duty/clearing. The receiver can record those charges as evidence without affecting inventory cost, or explicitly distribute them by received supplier-cost value.
- The purchasing receive API now accepts and validates the same shipping/duty and allocation fields as the staff receiving UI; API receipt/line responses expose landed-cost treatment and cost snapshots.
- API purchase receiving also forwards package counts, cartons and serial/IMEI identifiers to the authoritative stock-receipt service instead of discarding fields validated by the serializer.
- Supplier unit cost and landed unit cost remain separate immutable receipt-line snapshots. Weighted-average outlet cost uses the landed unit cost only when distribution was explicitly selected.
- Landed-cost distribution fails closed if any received line lacks supplier unit cost or if the received supplier-cost value is zero; it never invents a basis.
- Delivery history shows freight, duty/clearing, allocation treatment and landed unit cost per received line.
- Supplier-product relationships now carry an optional planning cost and one preferred-supplier flag per product, reusing the existing supplier code/package mapping rather than adding a parallel supplier catalog.
- New purchase orders can preselect a preferred supplier from stock planning. If the buyer leaves unit cost blank, the server suggests the selected supplier's configured planning cost, falling back to that supplier's latest physically received unit cost; an entered quoted cost always takes precedence.
- Supplier management now shows latest and previous received supplier cost plus cost movement, while receipt snapshots remain the immutable evidence source. Planning/default cost never rewrites historical receipts or outlet weighted-average cost by itself.
- Stock planning and CSV exports include preferred supplier, supplier code and planning cost. The PO handoff carries supplier, outlet, product and suggested quantity without auto-ordering.
- Supplier cost-history reads are batched per supplier screen to avoid per-SKU query growth on large catalogs.
- Purchase approval now reuses the existing draft PO instead of introducing a duplicate requisition ledger: storekeepers may prepare a pending purchase request, managers approve/reject it, and only an approved draft may be marked sent to the supplier.
- Manager-created PO drafts are auto-approved to keep small-business administration fast; pending requests require a different authorized manager, and rejection requires a reason.
- Requesters can withdraw their own pending request. Managers have a dedicated Needs approval lane, and approval/rejection/withdrawal actions are audit logged.
- Approval state is exposed through the PO API/read model and the same send transition fails closed outside the staff UI.
- The existing Suppliers directory now includes an evidence-based 90-day/1-year performance view instead of a separate dashboard. Metrics remain separate rather than being collapsed into an arbitrary overall supplier score.
- Supplier performance currently reports mapped/preferred products, PO and delivery counts, average first-receipt lead time, on-time arrival rate for due orders, quantity fulfilled for received/due orders, supplier-return rate, and counts of latest cost increases/decreases/unchanged products.
- Overdue purchase orders with no physical receipt count as not on time; future orders do not. Return rate uses returns and received units from the same evidence window. Cost direction compares the latest two received supplier-cost snapshots per product.
- Optional tenant-wide minimum retail gross margin is now configurable in Business settings. Enforcement activates only for Retail/Supermarket products whose outlet cost basis is complete.
- Automatic promotions that would breach the trusted-cost margin floor are hidden and rejected server-side; automatic customer price-book rates fall back to ordinary price; wholesale tiers are rejected rather than silently selling below the configured floor.
- Manager-approved manual line discounts may cross the floor only when the approval intent includes an explicit margin-override reason of at least eight characters. The override, configured floor, computed minimum unit price and proposed unit price are written to the existing audit ledger.
- Cost-incomplete merchandise remains intentionally non-blocking: the Stock screen exposes incomplete cost coverage for reconciliation instead of pretending a margin floor is reliable.
- Retail assembly builds now roll authoritative component outlet average costs through the configured BOM into a finished-unit cost. The build run snapshots each component quantity/unit cost plus the finished rolled-up unit cost for audit.
- Finished assembly stock uses the same weighted-average inbound costing engine as purchase receipts and transfers. If any BOM component cost is incomplete, the finished SKU remains explicitly cost-incomplete instead of inventing COGS.
- Assembly unbuild remains deliberately conservative: the finished SKU can be reduced without changing its average cost, but positive component recovery invalidates component cost trust because historical component-cost provenance is not yet sufficient for a safe reverse allocation.
- Legacy/incomplete positive stock can now be reconciled to a trusted average cost by an authorized inventory manager from the existing Stock balances screen. Reconciliation requires a documented evidence/reason, changes no quantity, cannot overwrite an already trusted basis, and does not rewrite historical sale cost snapshots.
- Cost reconciliation emits `inventory.cost_basis_reconciled` audit evidence with before/after values and explicit flags confirming quantity/history were untouched.
- Existing Stock balances now shows trusted inventory value, trusted-versus-incomplete stock coverage and a scoped CSV export. All calculations use the same authorized outlet and search filters as the listing; partial value is explicitly not described as total inventory value.
- Historical merchandise profitability now breaks trusted-cost coverage down by outlet/section and ranks products with the largest revenue exposure lacking trustworthy sale-time COGS. Management and sales CSV exports carry the same sections; unknown-cost revenue is never treated as zero-cost profit.
- Historical Retail/Supermarket margin exceptions now compare only trusted sale-time product/outlet profitability against the configured tenant retail minimum margin. Hospitality outlets and unknown-cost sales are excluded from the exception list; they remain visible through their own profitability/cost-gap reporting.
- Individual trusted-cost Retail/Supermarket sale lines below the configured margin floor are also retained as exceptions, so a later profitable sale of the same SKU cannot hide a manager-approved or otherwise below-floor transaction. These rows include sale reference, section, product identity, quantity, net revenue, historical COGS, gross profit and margin.
- Margin-breach reporting now quantifies the financial exposure, not only the percentage exception: each sale line records the gross-profit target implied by the configured floor plus the exact shortfall to that target; Management summarizes breach count, exposed revenue, known gross profit and total shortfall, links the sale reference back to the original order, and CSV exports preserve the same figures.
- Below-floor sale reporting now reuses the existing immutable sensitive-action approval trail instead of creating a second exception ledger. When a breach came from a manager-approved manual discount, reports show the cashier/requester, approving manager, override reason and approval time; breaches without matching approval evidence are explicitly marked as having no linked margin override rather than silently treated as authorized.
- The approval attribution is resolved in bulk after breach detection, so ordinary checkout and non-breach profitability rows do not gain per-line approval queries. Management, Sales Summary, CSV and scheduled owner PDF surfaces share the same attribution fields.
- Loss-prevention benchmark check (Lightspeed Retail employee/line reports, Shopify POS staff/product/location reporting, Square discount/void reporting, 2026-10-27): preserve staff, product and location dimensions and keep discounts/voids/refunds as explicit auditable measures instead of collapsing them into an opaque risk score. The implemented pattern tables follow that design and reuse the same underlying exception/audit/inventory evidence.
- Retail reporting benchmark check (Lightspeed R/X/S and Shopify profit reporting, 2026-10-27): keep sale-time COGS, gross profit and margin inspectable at line/product/outlet scope; do not substitute current cost for historical cost. Our implementation follows that pattern while adding an explicit configured-floor shortfall metric so managers can prioritize loss exposure without introducing a separate dashboard.
- Historical merchandise profitability now reports net revenue, revenue with trusted sale-time cost, revenue without trusted sale-time cost, known net COGS, known gross profit and known margin. Unknown-cost returns stay in overall net revenue but are excluded from the known-profit revenue pool instead of being treated as zero-cost.
- Sales, Management and CSV exports expose the same covered/uncovered revenue basis plus category profitability derived from immutable sale-time cost snapshots. Category figures inherit the same incomplete-cost, refund-attribution, outlet-scope and currency rules as product profitability.
- New merchandise sale lines also snapshot the category name used for historical category reporting, so moving or renaming a product category later does not rewrite old category profitability. Pre-snapshot legacy lines fall back to their current category.
- The category snapshot is finalized again at full-settlement stock posting alongside the authoritative COGS snapshot. This makes the historical classification reflect the completed sale, covers alternate line-creation paths, and avoids depending solely on when the item first entered an open basket.
- Sale lines now also snapshot SKU and whether the merchandise was inventory-tracked. Historical profitability prefers these snapshots, so later product renames, SKU changes, inventory-tracking changes, or a removed product relation do not erase the sale from COGS/profit reporting. Legacy lines without these snapshots continue to fall back to the current catalog relationship.
- Product profitability rows are keyed by sale-time name/SKU identity as well as product identity. If a catalog item is renamed or re-SKU'd later, old and new sales stay as separate auditable rows while totals remain combined correctly.



- Scheduled owner PDF/CSV reports expose the same covered/uncovered revenue basis; the PDF includes a category-profitability table rather than presenting known gross profit without its cost-coverage context.


- Sales Summary now reuses the same historical merchandise-profitability service as scheduled owner reports. COGS comes only from immutable sale-time cost snapshots; current stock cost is never substituted for missing historical cost.
- Interactive HTML, CSV and scheduled owner reports now share the same cost-coverage, return and attribution rules. Selected-outlet reports pass the exact same outlet scope into profitability as the sales totals.
- The sales-summary API now exposes the same tenant/outlet-scoped historical merchandise-profitability payload, so API, HTML, CSV and scheduled reports no longer use divergent COGS definitions.
- Completed merchandise sales are recognized once on the final POS payment date so installment payments spanning report periods do not duplicate full sale revenue/COGS. Exact line returns use original sale cost; restocked returns reverse COGS on the return date; unattributed refunds remain explicit coverage gaps instead of being guessed.

- Management → Reports now includes historical merchandise profitability derived from each sale line's immutable cost snapshot, never today's average cost. It reports net merchandise revenue, known net COGS, known gross profit/margin, cost coverage and product-level gaps.
- Physical line returns reverse sale-time merchandise revenue; COGS reverses only when stock was actually restocked. General/unmapped refunds, incomplete restock costs and historical foreign-currency payments are surfaced as coverage warnings instead of being guessed into product margin.
- Profitability uses the same authorized outlet/date scope as management reporting and exports CSV with spreadsheet-formula protection.
- Scheduled owner PDF/CSV reports now include the same merchandise profitability coverage and use the property's operating-day boundary when a property-specific schedule is configured; business-wide schedules retain the existing UTC calendar convention.
- RFQ sourcing is now implemented end to end: request lines → supplier invitations/responses → side-by-side quote comparison → guarded award → existing approved draft PO → reverse sourcing traceability. Supplier scorecards consume RFQ outcomes without creating a second supplier ledger.
- Supplier-product ordering terms now include optional minimum base-unit order quantity and expected lead days. These terms are visible during PO planning, enforced server-side at creation/send, and never overwrite an explicitly chosen delivery date.

- Cross-target Buy-X-Get-Y pricing now caps the free discount against the reward pool rather than the qualifying pool, so a more expensive reward can be fully discounted when the configured deal intends it.

Margin-floor enforcement is now active only when `cost_basis_complete=True`. Automatic promotions, customer price books and wholesale pricing cannot cross the configured floor on trusted-cost merchandise; manager-approved manual discounts require an audited override reason. Incomplete/legacy stock remains non-blocking until reconciled through an approved cost-bearing workflow.

## Workstream R4 — Sourcing, purchasing and supplier intelligence

**Goal:** complete the front half of purchasing before the already-strong PO/receiving/invoice/credit/payment back half.

**Maps to:** phases 07, 09, 18, 20, 21, 22, 32; SM-10, SM-16, SM-19, SM-31, SM-36.

### R4.1 Purchase requests / approvals
- Implemented by reusing the existing draft purchase order as the request record; no duplicate requisition ledger.
- Storekeepers can prepare a pending request for an authorized outlet; manager-created drafts are immediately approved.
- Pending requests require a different authorized manager to approve or reject before supplier send; rejection requires a note and requester withdrawal is supported.
- A dedicated Needs approval lane surfaces pending requests to managers; approval state is also exposed through the API and audited.
- Optional requester context is now implemented on the existing draft-PO request: Needed by is stored separately from supplier expected delivery, Request reason is visible to approvers and captured in approval audit evidence, and the Needs approval lane prioritizes the earliest stated need date with undated requests last.
- Approved-request consolidation is now implemented as an optional manager lane for centralized procurement. Two or more approved unsent drafts may be combined only when they share the same supplier and receiving section; duplicate SKU quantities are summed only when unit costs agree exactly.
- The resulting PO is a new approved draft using base-stock quantities. Original requests are not deleted or rewritten: each source is linked through `consolidated_into`, retains requester/needed-by/reason/package/approval evidence and is closed from supplier-send flow. The consolidated PO links back to every source request.
- Consolidation locks source PO and line rows transactionally, rejects mixed suppliers/sections, previously consolidated requests, financial/receiving evidence and conflicting SKU costs, and caps one action at 50 source requests.
- Benchmark check (Lightspeed Retail master orders and purchase orders, 2026-10-27): centralized purchasing may assign multiple stock needs into vendor/location purchase orders, while the purchasing document remains the commercial order and source requirements remain traceable. Our implementation follows that pattern without introducing a separate requisition ledger.

### R4.2 RFQ and quotation comparison
- Implemented as a manager-only, tenant/outlet-scoped sourcing workflow under Purchasing → Supplier quotes.
- One RFQ records the receiving outlet, needed-by date, specification/notes and requested base-stock quantities once; multiple active suppliers can then be added against the same requirement.
- Supplier quote evidence records reference, line unit prices, quantity availability, promised dates, freight, other quoted charges, lead time, payment terms and quote validity separately.
- Comparison shows item subtotal, freight, other charges, total quoted cost, lead time and availability. Lowest price is highlighted only among complete quotes that can fulfil every requested quantity; it is evidence, not an automatic supplier decision.
- Awarding requires a complete, non-expired, fully available quotation. Exactly one quote wins the RFQ and converts transactionally into the existing approved draft PO flow using quoted item unit costs.
- Quoted freight/other charges remain sourcing evidence and PO notes; actual landed cost is still recorded from the physical delivery, so a quotation never silently changes inventory valuation.
- Awarded POs link back to their RFQ/quote in both staff UI and the purchase-order API. Closed RFQs lock all quote editing, and unawarded RFQs can be cancelled only with a recorded reason.
- RFQ/quote tables carry tenant ownership and PostgreSQL RLS from their creation migration; create/invite/record/award/cancel actions are audit logged where state changes occur.
- Current rollout intentionally awards one complete supplier quote for the whole RFQ. Split awards/partial-line sourcing, external supplier email delivery and supplier self-service quotation portals remain deferred until operational demand justifies them.

### R4.3 Product/vendor relationship
- Preferred and alternate supplier relationships are implemented on the existing supplier-product/package mapping; supplier codes remain purchasing-only and never become cashier barcodes.
- Supplier-specific planning cost, supplier/package code, physical receipt cost history and preferred-supplier designation are implemented.
- Optional minimum order quantity and expected lead days are now stored per supplier-product relationship. MOQ is enforced when a PO is created and rechecked before supplier send; lead time suggests an expected date only when the buyer has not entered one.
- Product/package purchase sizing continues to use the existing package and base-unit snapshots, so MOQ is evaluated against actual base-stock quantity rather than display pack text.
- Effective-dated supplier price records are now exposed in the supplier product-catalog UI and can be maintained individually or imported in bulk from a validated UTF-8 CSV. Imports match only existing tenant stock by supplier code or SKU, including package-specific supplier codes; they never create products.
- Supplier price-list import is preview-first and all-or-nothing: row/file limits, numeric/date validation, duplicate target detection and tenant-safe identifier resolution run before a signed server-generated preview is produced. Apply accepts only that signed preview and rechecks that the matched product/package is still active.
- Re-importing the same supplier/product/package/minimum/effective/source key updates that planning record rather than multiplying duplicates. Import audit evidence records file name, row count and create/update counts.
- Planning supplier prices remain separate from received-cost evidence, weighted-average inventory cost, historical COGS and retail price. A price-list import cannot rewrite any of those facts.
- Supplier comparison is now embedded in the existing purchase-request/PO creation screen when stock planning prefills an item and quantity. It compares current eligible effective price-list cost, supplier default planning cost and latest received-cost fallback, while showing MOQ, lead time, preferred relationship and supplier code separately.
- “Lowest” is highlighted only among suppliers that are currently eligible for the requested quantity and have a known planning cost. A cheaper supplier below its MOQ is shown as ineligible rather than being recommended, expired price-list rows are ignored, and no supplier is auto-selected or awarded.
- Comparison remains tenant-scoped and evidence-based; received-cost snapshots remain the factual purchasing history and the buyer must still choose the supplier. Benchmark check (Lightspeed Retail vendor/default cost and Square vendor/unit-cost workflows, 2026-10-27): vendor identity/code, vendor cost and actual received unit cost are maintained as distinct purchasing evidence rather than collapsed into an opaque supplier score.

### R4.4 Landed cost
- Shipping/freight and duty/clearing are implemented at physical receipt level.
- Allocation methods now include: exclude from inventory cost, distribute proportionally by received supplier-cost value, distribute proportionally by received base quantity, or enter an explicit manual amount per received line.
- Manual allocations are fail-closed: every received line still needs a real supplier unit cost, each manual amount must be finite/non-negative, and the line allocations must total freight + duty exactly before any receipt, stock movement or weighted-average cost update is posted.
- Automatic by-cost and by-quantity modes allocate rounding residual to the final received line so the stored per-line allocation always reconciles exactly to the receipt-level landed-cost total.
- Original supplier unit cost, line allocated landed cost and landed unit cost remain separate immutable receipt-line snapshots. Landed unit cost feeds the authoritative outlet weighted-average inventory cost and therefore future sale COGS/margin snapshots.
- A separate generic “allocate by weight” mode is deliberately not implemented because the catalog does not have one trustworthy physical weight-per-base-unit attribute across all merchandise. Weight-UOM products already express received quantity in their stock unit; adding a second guessed weight basis would create false precision.
- Post-receipt landed-cost correction/credit handling is now implemented as an append-only evidence workflow. Original receipt snapshots are never rewritten; the adjustment records its own reference, reason, signed amount, allocation method and per-line amounts.
- A correction may revalue current weighted-average inventory only when every affected stock balance is complete/positive and no outbound stock movement has occurred for any affected item since that receipt. If stock has already been sold, transferred, returned, wasted or adjusted out, correction fails closed because part of the original cost may already belong in historical COGS.
- Credits cannot reduce cumulative landed cost below zero. Corrections change no stock quantity, cash, supplier payable, supplier credit-note record or historical sale snapshot; those remain separate workflows.
- Evidence-based profitability recommendations are now implemented in Management → Reports and the profitability CSV. The queue prioritizes missing trusted cost, trusted-cost retail margin-floor shortfalls, unattributed merchandise refunds and foreign-currency scope gaps without auto-changing retail prices, supplier costs, historical COGS, refunds or policy settings.
- Benchmark check (Lightspeed Retail advanced reporting/inventory performance and Shopify profit reports, 2026-10-27): profit reporting should preserve cost-at-sale semantics, show COGS/gross profit/margin by product/location, and make missing cost visible instead of silently substituting current cost. The action queue follows that evidence-first model and keeps operational correction separate from historical reporting.
- Remaining: historical-cost reconstruction for assembly unbuilds.

### R4.5 Supplier performance
- Implemented on the existing Suppliers directory rather than a separate dashboard.
- Evidence-based metrics include first-receipt lead time, on-time rate, due-quantity fulfilment, supplier-return rate, latest received-cost direction, received supplier-cost value, mapped/preferred products and PO/delivery counts.
- RFQ outcomes now add quotes received, wins, losses, no-response count and win percentage. No arbitrary blended supplier score is generated; managers see the underlying measures separately.
- Received value is based on physical receipt quantity × supplier unit-cost snapshot; it is not confused with cash paid, landed cost, invoice settlement or full accounting spend.

**UI surfaces:** Requisition inbox, approval screen, RFQ, quotation comparison, supplier product tab, landed-cost allocation, supplier scorecard.

## Workstream R5 — Fulfillment, delivery and multi-location stock

**Goal:** make stock movement and customer fulfillment explicit across branches, warehouse and delivery workflows.

**Maps to:** phases 07, 09, 15, 16, 18, 25; SM-24, SM-27, SM-28, SM-32.

### R5.1 Warehouse/location model
- Allow non-selling warehouse/storage outlets.
- Central warehouse replenishment.
- Branch allocation proposals.
- Keep existing tenant/site/outlet architecture.

### R5.2 Transfer lifecycle
- Request → approve/reject → dispatch → in transit → receive/dispute → resolve is now implemented around the existing staged transfer ledger.
- A transfer request is explicitly non-ledger: creating or approving it changes no stock. Source stock moves only at dispatch; destination stock moves only after physical receiving.
- Storekeepers can request stock for a destination they operate even when the source is another branch. A different source-side manager must approve/reject; approved quantity cannot exceed the request or current source stock.
- Approved requests dispatch through the existing staged-transfer service, preserving source cost snapshots, batch identity, in-transit custody, independent receiving, discrepancy handling and resolution.
- Requester cancellation, rejection reasons, approval/dispatch audit events, tenant RLS and role-specific request/approval permissions are implemented.
- Manager direct dispatch remains available as a fast path for simple businesses; direct transfers retain the stricter rule that the actor must be authorized for both source and destination.
- Printable transfer documents/packing slips are implemented from the authoritative transfer receipt, showing source/destination custody, product/quantity, dispatch/receive staff, source request and discrepancies. Access is limited to staff authorized for the source or destination section.
- Remaining: optional picked/packed state, multi-line transfer requests, damaged-in-transit classification and richer custody timestamps.

### R5.3 Customer fulfillment
- Pickup.
- Delivery.
- Partial fulfillment.
- Picking and packing.
- Packing slip.
- Delivery address.
- Delivery fee.
- Courier/driver assignment.
- Tracking/reference.
- Delivered/failed/returned status.
- Proof-of-delivery note/photo hook.
- External courier APIs deferred.

### R5.4 Shelf/bin operations
- Existing shelf locator extended to zones/bins.
- Mobile pick/count flows.
- Bin-aware count worksheet without creating a second stock ledger unless quantity-by-bin becomes an approved requirement.

**UI surfaces:** Warehouse dashboard, transfer board, pick/pack queue, delivery board, bin/shelf mobile screens.

## Workstream R6 — Workforce, controls and loss prevention

**Goal:** combine employee operations, permissions and fraud controls in one management area.

**Maps to:** phases 01, 03, 04, 18, 20, 21, 22, 26; SM-07, SM-20, SM-29, SM-33, SM-35.

### R6.1 Role/permission templates
- Built-in reusable role presets remain business-line aware, and the workspace now has a dedicated Roles & access screen with permission previews derived from the existing enforced base-role policies.
- Tenant-custom saved role templates are implemented as a safe base role plus default branch/outlet scope. Templates cannot package owner/tenant-admin access, cannot reference another tenant's branches/outlets, and cannot grant capabilities beyond the selected built-in base role.
- Saved templates can be applied during worker creation/editing and through bulk team actions. Applying a template copies its current role/scope to the worker and records the template source in membership/audit evidence.
- Template edits are deliberately non-retroactive: changing a template does not silently rewrite live workers; an administrator must re-apply it intentionally. Built-in presets and saved templates are mutually exclusive on one submission to avoid ambiguous access.
- Roles and templates stay filtered by the tenant's configured business lines and existing outlet-type compatibility rules. Existing site/outlet scoping remains authoritative and fail-closed.
- Role administration is audit logged, templates can be made inactive instead of requiring destructive deletion, and the Members directory shows each worker's last-applied template.
- Benchmark check (Lightspeed Retail employee roles/access and Shopify POS staff roles/location access, 2026-10-27): use named reusable roles, explicit task permissions, location assignment and individual worker identity; our implementation keeps the same understandable model while preserving the stricter tenant/business-line/outlet scope already enforced by this POS.

### R6.2 Time and attendance
- Worker self-service attendance is implemented at /staff/attendance/: clock in, start/end break and clock out are explicit state transitions with audit events and one-open-shift / one-open-break database constraints.
- Attendance is a separate workforce ledger from POS cash/register shifts. Clocking in/out never creates, closes or reconciles a PosShift; register accounting remains independent.
- Each attendance shift records the worker membership, branch, optional sales area, clock-in/out timestamps, notes, breaks and review state. Gross, break and worked hours are calculated from the attendance record rather than inferred from POS activity.
- Managers have a scoped Timesheets screen with date/status/worker filters and CSV export. Only owner, tenant-admin, site-manager and outlet-manager roles can review timesheets, and they only see workers in their authorized branch/outlet scope.
- Clocked-out shifts enter Pending review. Managers can approve them or correct clock-in/out times with an explicit correction note; corrections are audit logged with before/after values.
- Corrections fail closed if they would overlap another attendance shift for the worker or place an existing break outside the corrected work interval. Open shifts cannot be approved/corrected, and workers must end an active break before clocking out.
- Late/absence notes remain a scheduling-stage enhancement because the system does not yet have a published work schedule against which lateness/absence can be determined truthfully.
- Benchmark check (Lightspeed Retail employee hours and Square Shifts/timecards, 2026-10-27): separate work-time tracking from register operations, support worker clock in/out and breaks, provide manager review/edit controls, and retain location/worker filters and export. Our implementation follows that model while preserving tenant/site/outlet scope and audited correction evidence.

### R6.3 Commissions and targets
- Tenant commission rules are implemented for worker, product, category, tenant-wide default, and worker + product/category combinations. Owner/tenant-admin manage the rules from Workspace → Commissions; rate, target objects and effective dates are tenant-scoped and audit logged.
- At final sale completion the POS freezes the credited worker, rule name, net commission base, rate, amount and commission settlement timestamp onto each non-void sale line. Partial payments earn nothing until the final settlement; folio-charged completed sales use the same snapshot path even without a POS payment row.
- Rule matching is deterministic: the most specific matching active rule wins, with worker-specific scope taking precedence before product/category when specificity ties. The UI rejects overlapping active rules with the same worker/product/category scope and effective period so administrators cannot create ambiguous same-scope rules.
- Settled history is immutable. Editing a commission rule never recalculates previously settled sale lines; reports use the frozen snapshots rather than today's commission configuration or catalog state.
- Return/refund adjustments are recognized in the period when the return/refund occurs, even when the original sale belongs to an earlier period. Exact retail line returns reverse the corresponding frozen line sales/commission proportionally by returned quantity. General order refunds that do not identify an item are explicitly allocated proportionally across that sale's frozen attributed lines; refunds with no commissionable attributed lines remain visible as unallocated refund exposure rather than being guessed onto a worker.
- A current period may therefore show negative net commission when it contains clawback evidence from earlier sales. This is a reporting adjustment only: the POS does not automatically deduct employee pay.
- Management → Commissions & targets is implemented for owner/tenant-admin/site-manager/outlet-manager within their existing branch/outlet scope. It reports gross attributed sales, sales reversals, net sales, gross commission, exact return reversals, allocated general-refund reversals and net commission, with CSV export.
- Sales targets are manager-scoped, non-overlapping per worker, support future planning periods and can be edited with audit evidence. Target progress uses net attributed sales after return/refund adjustments and is shown only when one target covers the complete selected report period; payroll payment remains out of scope.
- Benchmark check (Lightspeed Retail line-employee/commission reporting and Shopify POS staff attribution/net-sales reporting, 2026-10-27): preserve employee attribution at the sale line/transaction boundary, report employee performance from explicit sale attribution, and include returns/refunds in net performance rather than reporting gross-only commission. The implementation follows that model while adding immutable settlement snapshots and explicit cross-period reversal evidence.

### R6.4 Loss prevention
- No-sale drawer-open evidence once hardware exists.
- Price overrides.
- Repeated void/refund patterns.
- Excess discount patterns.
- Margin-floor override exceptions now appear in the existing Management → Exceptions/Cases workflow even when the discount amount itself is below the generic large-discount threshold. Each exception carries outlet/product, configured floor, minimum allowed unit price, actual approved unit price, cashier, approving manager and override reason, and can use the existing review/assignment/follow-up/resolution trail.
- Cash variance trend.
- Shrink/write-off trend.
- Explainable worker/section/product pattern tables are now implemented in Management → Exceptions for the configured review window. Refunds, voids, manual line discounts, margin-floor overrides, cash variances and negative stock-removal events remain separate counts; the system does not invent a composite fraud score or combine monetary values across currencies.
- The grouped loss-prevention view is exportable as a scoped CSV using the same worker/section/product evidence and lookback window. Management's profitability CSV is also aligned with the shared Sales CSV for below-floor sale target gross profit, margin shortfall, cashier, linked manager approval, override reason and approval time, removing a reporting divergence between the two management surfaces.
- Cashier/product/outlet heat maps remain a visual enhancement on top of the implemented grouped evidence, not a separate data model.
- Worker, section and product pattern rows now drill into the exact underlying refund, void, discount/margin-override, cash-variance and stock-removal evidence in the manager's current scope. Product drill-down deliberately excludes refunds/cash variance because those sources do not prove a product attribution. Source links reopen the original receipt, shift reconciliation or exact scoped stock movement rather than copying evidence into a second ledger.
- Cash variance is attributed to a named worker pattern only when the same worker both opened and closed the POS shift. Shared/legacy shifts with different or missing operators remain in the outlet pattern but use an explicit Unknown/shared attribution worker bucket, avoiding unsupported blame assignment.
- Pattern drill-down and CSV export use the complete scoped evidence set; only the on-screen summary table is capped for readability.
- Loss-pattern evidence drill-down now supports explicit evidence-type filters (refund, void, line discount, margin override, cash variance, stock removal where attributable) and a scoped CSV export of the exact underlying evidence. Invalid/unavailable filter values fail closed rather than creating empty synthetic categories.
- Manager investigation trail.

**UI surfaces:** Roles & permissions, attendance board, timesheets, commission rules/reports, loss-prevention dashboard.

## Workstream R7 — Accounting bridge and management reporting

**Goal:** produce accounting-ready operational data without pretending the POS is already a complete general ledger.

**Maps to:** phases 10, 17, 18, 19, 22, 32; SM-13, SM-19, SM-23, SM-29, SM-31, SM-36.

### R7.1 Operational accounting dimensions
- Provider-neutral accounting mappings are implemented for default/category revenue, sales returns, tender clearing by payment method, tax/VAT liability, default/category inventory asset, default/category COGS, accounts receivable and accounts payable.
- Completed POS sales are recognized once at final settlement. Revenue is split by sale-time category after proportional order discount, VAT/tax is separate, and tender debits use net retained payment amounts by method at settlement so split/partial tender remains balanced even when a payment was refunded before completion.
- Trusted sale-time inventory cost produces paired COGS debit / inventory credit entries. Inventory-tracked lines without trusted cost are explicitly counted and warned; the bridge never treats unknown cost as zero.
- Refunds are recognized in the refund period: tender clearing is credited, sales returns are debited for the pre-tax portion, and VAT/tax liability is proportionally reversed from immutable order totals.
- POS orders charged to guest folios debit any retained POS tender plus Accounts Receivable for the unpaid balance, then credit revenue/tax and trusted COGS/inventory. Later folio payments debit tender clearing and credit A/R.
- Fully matched supplier invoices debit inventory asset by matched product category and credit Accounts Payable. Supplier payments debit A/P and credit the mapped tender/bank clearing account. Supplier invoices whose matched immutable lines do not equal the invoice total block export instead of guessing the difference into inventory or expense.
- Journal rows carry branch, outlet, register, cashier, tender, category, folio and supplier dimensions where the operational source proves them.
- Operational source references are preserved on journal rows. POS/folio/supplier settlement sources also resolve through the existing FinancePostingLink to the corresponding cashbook entry when one exists, giving journal → source transaction → cashbook traceability without a second posting ledger.
- Accounting mapping and export-history tables have PostgreSQL tenant RLS policies and remain scoped by the existing membership/site/outlet rules.

### R7.2 Accounting export/integration boundary
- Workspace → Accounting mappings is implemented for owner/tenant-admin setup. Category and tender sources are selected through tenant-scoped forms rather than manual UUID entry; duplicate source mappings fail validation and mappings may be made inactive instead of destructively deleted.
- Accounting export is implemented for owner, tenant-admin and accountant roles within their authorized outlet scope. The preview validates required mappings, operational match constraints and debit=credit balance before enabling export.
- Generated AccountingExportBatch records freeze date range, outlet scope, mapping snapshot, journal lines, source summary, totals, generator and fingerprint. Re-generating an identical preview reuses the existing batch; later mapping edits create a new fingerprint and cannot mutate historical exports.
- Journal-ready CSV is spreadsheet-formula safe and includes accounting accounts, debit/credit amounts, operational dimensions and source references. Historical downloads re-check the user's current outlet scope and fail closed if the batch includes outlets no longer visible to that user.
- A provider-neutral AccountingExportAdapter boundary is implemented; Journal CSV is the first adapter. Future QuickBooks/Xero/Sage connectors must consume the immutable export batch rather than embedding provider-specific account IDs or API behavior in POS settlement/accounting logic.
- Mapping preview and export are read/export operations only. Existing CashbookEntry and FinancePostingLink records remain authoritative operational postings and are never duplicated or rewritten by the accounting bridge.
- Provider-specific API integrations, bank feeds and a full general ledger remain deliberately out of scope until a provider is selected.
- Benchmark check (Lightspeed accounting mapping/export patterns, 2026-10-27): map revenue/discount/payment/tax/inventory/COGS dimensions to accounting accounts, validate the mapping before activation/export, preserve location/source dimensions and keep provider sync behind an integration boundary. The implementation follows that model while retaining immutable POS/PO/refund/folio source evidence.

### R7.3 Management reporting
- Sales by hour/day/branch/outlet/register/cashier/category/item.
- Margin only where verified cost exists.
- Inventory valuation and ageing.
- Historical stock snapshots where data supports them.
- Customer ranking/frequency/inactivity.
- A/R ageing.
- Supplier performance/payables.
- Promotion performance.
- Refund/void/discount/variance trends.
- Basket-size and product-affinity analysis.
- Export and scheduled delivery using existing reporting infrastructure.

**UI surfaces:** Accounting mapping/export, executive dashboards, drilldown reports, report scheduler.

## Workstream R8 — Hardware, training and rollout completion

**Goal:** finish the operator-facing environment after the business workflows are correct.

**Maps to:** phases 15, 16, 27, 28, 31, 33; SM-03, SM-12, SM-15, SM-21, SM-28, SM-33, SM-34.

### R8.1 Hardware adapters
- Workstations now have an explicit tenant-scoped device registry for receipt printers, kitchen printers, cash drawers, barcode scanners, weighing scales and customer displays. Each device records its adapter mode, label, active state, health evidence, failures/latency and recent telemetry; PostgreSQL RLS protects the registry.
- Adapter policy is explicit and fail-closed. Browser print, keyboard-wedge input and paired-browser display remain supervised browser capabilities and are never described as proof that physical hardware is online. Direct control is only available through the local hardware bridge adapter.
- A generic local hardware bridge boundary is implemented with revocable one-time credentials, tenant/workstation binding, authenticated poll/report API, command idempotency, claim timeout, expiry, bounded retry/backoff, result/error evidence and device-health updates. Raw bridge secrets are shown once and stored only as hashes.
- Receipt and kitchen printers support local-bridge ping plus non-financial test-print command envelopes. Existing browser receipt printing remains available as a fallback and still requires the operator to confirm the actual physical print.
- Cash drawers support a local-bridge open command, but Equipment Check deliberately cannot invoke it. A drawer-open command is queued best-effort only after a committed cash payment tied to an open workstation shift; hardware failure cannot roll back or duplicate the payment, and payment replay cannot queue a second drawer command.
- Weighing scales support local-bridge ping, read and tare commands. Existing scale-label/barcode support remains separate from live weight telemetry.
- Customer-facing display remains the existing cashier-specific paired browser display that mirrors only the active basket and hides previous/customer/payment-method details. It is represented as a registered device without converting browser presence into fake physical-device health.
- Barcode scanner diagnostics now measure one rapid keyboard-wedge burst locally (character count, elapsed time, average/max inter-key gap and Enter terminator) without mutating a basket. Only timing/count evidence is persisted; the barcode value itself is never stored. Scanners can also be represented by a local-bridge adapter without converting browser input into fake scanner identity telemetry.
- Equipment Check now shows registered device status, adapter capabilities, retry limits, recent bridge commands and staff-observed checks in the existing Workstations area instead of introducing another hardware dashboard.
- Card/mobile-money provider hardware remains deferred until a provider and production credentials are selected.
- Benchmark check (Lightspeed Hub/Hardware and Square hardware setup, 2026-10-27): configure hardware per register/station, provide device test/status surfaces, couple printer-driven drawers to authorized sale flows, and surface connection problems quickly. Our bridge follows that pattern while keeping browser fallbacks and physical-device certification explicitly separate.

### R8.2 Training mode
- Training is implemented as an isolated tenant type (`Tenant.is_training`), chosen only when the workspace is created. Platform edit forms disable the field afterward and regression coverage proves a crafted edit POST cannot convert training ↔ live.
- Staff, Console and customer-display surfaces carry a permanent TRAINING WORKSPACE warning. The customer display explicitly states that the basket is a practice transaction rather than a live customer checkout.
- Retail/Supermarket training has a deterministic managed sample pack: four barcode/SKU products with trusted inventory cost, one low-stock item, one sample customer, one supplier, a draft purchase order, one completed sale, one refund and one physical-return record. The sample sale uses the tenant currency and the real internal payment/stock/finance services.
- Guided cashier, storekeeper and manager exercise checklists are available from Console → Training and link to the real checkout, inventory, purchasing, sales, management and accounting screens. Checklist completion is stored separately from transaction truth; marking an exercise complete never fakes the underlying operation.
- Reset is password-confirmed and requires the exact phrase `RESET TRAINING`. It deletes/recreates only the objects owned by the managed sample pack and clears exercise progress. Tenant identity/settings, domains, users/memberships, branches/sections, workstations, paired browsers and hardware configuration are preserved.
- Managed sample object IDs are stored in a tenant-scoped `TrainingWorkspaceState` with generation number, seed audit metadata and PostgreSQL RLS. Reset uses those exact IDs instead of guessing rows by name.
- Live tenants cannot seed/reset training data or open the guided training controller.
- EFRIS is hard-disabled for training tenants even if global and tenant fiscal settings are accidentally enabled. Local hardware-bridge commands are also rejected in training workspaces, so practice sales cannot print/open drawers/read scales through live hardware.
- The existing read-only Setup → Practice checkout remains available as an even safer calculation-only rehearsal that creates no Order/Payment/StockMovement.
- The local `create_training_demo` development command now marks created tenants explicitly as training; its existing DEBUG + disposable SQLite restrictions remain unchanged.
- Retail/Supermarket is the first production training pack. Hospitality training will reuse the same isolated-tenant boundary rather than mixing hospitality sample data into this retail reset pack.

### R8.3 Acceptance
- The existing exact-commit release certificate is now the R8 acceptance gate; it already runs deployment checks, migration drift/applied checks, the full automated suite and static collection, then requires independent evidence files for PostgreSQL, browsers, restore and rollback.
- External evidence can no longer be a generic passing JSON. The certificate requires explicit coverage tokens: desktop/laptop/tablet/phone, keyboard/touch/scanner input; PostgreSQL tenant RLS, multi-register concurrency, settlement idempotency and inventory concurrency; backup/restore/data consistency; and git/migration/static/service rollback evidence.
- When retail hardware is advertised, `--require-hardware` now requires explicit receipt-printer, barcode-scanner, cash-drawer, weighing-scale and customer-display coverage on the exact commit. Queue success, browser capability or a configured device label is not accepted as physical proof.
- `docs/RETAIL_R8_ACCEPTANCE_REGISTER_2026-10-27.md` records SOURCE IMPLEMENTED vs AUTOMATED VERIFIED vs STAGING VERIFIED vs PHYSICAL VERIFIED so rollout status cannot be overstated.
- Desktop/laptop/tablet/phone and keyboard/scanner/touch remain staging/browser evidence requirements, not source-code claims.
- PostgreSQL/RLS and multi-register concurrency remain exact-commit staging evidence requirements in addition to CI policy/integration checks.
- Restore and rollback remain independently rehearsed evidence requirements; the release tool never performs destructive restore/rollback operations itself.
- Real printer/scanner/drawer/scale/customer-display trials remain PENDING until actual named devices are tested. R8.1 source implementation does not change that status.
- Exact-head CI must finish successfully and all required exact-commit evidence must pass before the release may be described as certified.

## Execution sequence

| Order | Workstream | Why this order |
|---|---|---|
| 1 | R1 Merchandise master | Variants/packages/serials/bundles are dependencies for pricing, purchasing and fulfillment. |
| 2 | R2 Pricing & promotions | Depends on reliable concrete SKUs/variants/packages. |
| 3 | R3 Customer commerce | Credit, orders, layaway, exchanges and gift/store credit share customer and pricing foundations. |
| 4 | R4 Sourcing & purchasing | Builds on products/packages/costs and connects to the existing mature PO backend. |
| 5 | R5 Fulfillment & multi-location | Depends on customer orders, packages and supplier/warehouse flows. |
| 6 | R6 Workforce & controls | Applies governance across the now-complete operational journeys. |
| 7 | R7 Accounting bridge & reporting | Uses stable transaction/cost/customer-order semantics instead of reporting half-built concepts. |
| 8 | R8 Hardware/training/acceptance | Final device/provider-specific rollout after software contracts are stable. |

## First implementation batch — R1

Start with **R1.1 + R1.2**, but preserve simple products.

1. Inspect current MenuItem/SKU/packaging models and existing carton work.
2. Add product-family/variant option/value models only where existing fields cannot represent the requirement.
3. Add package definitions with package barcode and conversion to base stock unit.
4. Add tenant-safe migrations/RLS where applicable.
5. Add Console catalog UI: variant family editor, matrix creation, package editor.
6. Update search/scan resolver to accept package barcodes and resolve the concrete variant.
7. Keep basket line semantics in base sell quantity; package scan converts before calling existing add-line service.
8. Add tests for tenant isolation, duplicate barcode/SKU prevention, package conversion, scan resolution and unchanged simple-product behavior.
9. Update supermarket and phase trackers.
10. Require exact-head CI before marking the batch locally verified.

## Deferred payment-provider scope

Not included for now:
- card processor SDK/API,
- mobile-money API,
- tap-to-pay,
- Apple Pay / Google Pay,
- merchant settlement automation,
- chargeback API,
- provider webhooks.

The UI and domain model may expose generic payment-method placeholders, but no provider will be advertised as integrated until credentials, settlement semantics and production tests exist.
