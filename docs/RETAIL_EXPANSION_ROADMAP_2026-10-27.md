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
- margin-floor controls using the new authoritative outlet cost basis; only cost-complete merchandise may be protected automatically, with legacy/incomplete stock surfaced for reconciliation;
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
- This is weighted-average cost by outlet. Landed-cost allocation, supplier freight/duty distribution and assembly cost roll-up remain R4 work.

This checkpoint intentionally does **not** enable automatic margin-floor blocking yet. Margin-floor enforcement will use only balances where `cost_basis_complete=True`; incomplete/legacy stock must first be reconciled through approved cost-bearing workflows.

## Workstream R4 — Sourcing, purchasing and supplier intelligence

**Goal:** complete the front half of purchasing before the already-strong PO/receiving/invoice/credit/payment back half.

**Maps to:** phases 07, 09, 18, 20, 21, 22, 32; SM-10, SM-16, SM-19, SM-31, SM-36.

### R4.1 Purchase requisitions
- Staff/branch request.
- Needed-by date, outlet, product, quantity and reason.
- Draft/submitted/approved/rejected.
- Manager approval.
- Consolidate approved requests.

### R4.2 RFQ and quotation comparison
- Send/record RFQ against one or more suppliers.
- Supplier quotation header + line prices.
- Freight/other charges noted separately.
- Side-by-side comparison: unit cost, total, lead time, availability, terms.
- Approve winning quote.
- Convert approved quotation into existing PO flow.

### R4.3 Product/vendor relationship
- Preferred supplier.
- Alternate suppliers.
- Supplier-specific SKU/barcode.
- Supplier price list and effective dates.
- Minimum order quantity and pack size.
- Lead-time history.

### R4.4 Landed cost
- Freight, duty, handling and other landed charges.
- Allocation method: value/quantity/weight/manual.
- Preserve original supplier unit cost and landed unit cost separately.
- Margin warnings/recommended selling price based on approved cost policy.

### R4.5 Supplier performance
- On-time delivery.
- Fill rate.
- Price variance.
- Return/discrepancy rate.
- Spend.
- Quote win/loss.
- Supplier scorecard.

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
- Requested → approved → picked → dispatched → in transit → received/disputed → resolved.
- Custody and timestamps.
- Short/damaged receipt.
- Transfer document/packing slip.
- Existing stock transfer ledger remains authoritative.

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
- Reusable permission presets.
- Tenant-custom role definitions layered over safe capability primitives.
- Cannot grant cross-tenant/outlet access.
- Clear UI preview of what each role can do.

### R6.2 Time and attendance
- Clock in/out.
- Breaks.
- Shift attendance.
- Late/absence notes.
- Timesheet review/approval.
- POS shift remains financially separate from attendance shift.

### R6.3 Commissions and targets
- Commission rules by employee/product/category.
- Immutable sale attribution.
- Refund reversals.
- Commission report.
- Sales targets and progress.
- Payroll payment itself is out of scope.

### R6.4 Loss prevention
- No-sale drawer-open evidence once hardware exists.
- Price overrides.
- Repeated void/refund patterns.
- Excess discount patterns.
- Cash variance trend.
- Shrink/write-off trend.
- Cashier/product/outlet heat maps.
- Manager investigation trail.

**UI surfaces:** Roles & permissions, attendance board, timesheets, commission rules/reports, loss-prevention dashboard.

## Workstream R7 — Accounting bridge and management reporting

**Goal:** produce accounting-ready operational data without pretending the POS is already a complete general ledger.

**Maps to:** phases 10, 17, 18, 19, 22, 32; SM-13, SM-19, SM-23, SM-29, SM-31, SM-36.

### R7.1 Operational accounting dimensions
- Revenue category mapping.
- Inventory/COGS category mapping.
- Tender clearing mapping.
- Tax/VAT mapping.
- Supplier payable/customer receivable references.
- Branch/outlet/register dimensions.
- Immutable source links back to POS/PO/refund/customer account records.

### R7.2 Accounting export/integration boundary
- Period export.
- Journal-ready CSV.
- Mapping preview and validation.
- Export history/idempotency.
- Adapter interface for future QuickBooks/Xero/Sage integrations.
- Provider-specific integrations deferred until chosen.
- Do not build bank feeds or full GL in this phase.

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
- Direct receipt/kitchen printer adapter.
- Cash drawer.
- Scale/tare.
- Customer display.
- Scanner diagnostics.
- Card/mobile-money provider hardware is deferred.
- Retry/health/status around supported devices.

### R8.2 Training mode
- Explicit training tenant/mode banner.
- Sample product/customer/stock/sale/PO/return data.
- Guided cashier, storekeeper and manager exercises.
- Safe reset.
- No live provider or fiscal side effects.

### R8.3 Acceptance
- Desktop/laptop/tablet/phone.
- Keyboard/scanner/touch.
- Multi-register concurrency.
- PostgreSQL/RLS.
- Restore/rollback.
- Real printer/scanner/scale/customer-display trials.
- Exact-head CI and release evidence.

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
