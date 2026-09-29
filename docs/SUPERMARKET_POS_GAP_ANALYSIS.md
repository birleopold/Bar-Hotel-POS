# Supermarket POS Capability and Gap Analysis

This assessment compares the current platform with the operating capabilities expected from a professional supermarket POS. It distinguishes software workflows that are implemented today from physical-device and payment-provider integrations that still require dedicated adapters.

## Current coverage

| Capability | Status | Current implementation and boundary |
| --- | --- | --- |
| Product catalog | Implemented | SKUs, barcodes, PLU codes, departments, tax, unit of measure, weighted/fractional quantities, selling price, inventory tracking, and reorder levels. |
| Scan-heavy checkout | Implemented | Cashiers can add items by barcode or PLU and process weighted quantities. Common scanner devices that behave like keyboards can use this flow. A vendor-specific scanner SDK is not included. |
| Inventory deduction | Implemented | Completing a paid sale consumes tracked stock. Stock balances, movements, counts, transfers, low-stock views, and returns with optional restocking are available. |
| Purchasing | Implemented | Suppliers, purchase orders, order lines, status workflow, and partial goods receiving are available per branch and section. |
| Promotions | Implemented | Time-bound percentage promotions can be scoped to sections and applied to orders. Coupon codes, mix-and-match offers, and customer-specific price books are not yet modeled. |
| Payments | Implemented as recorded tenders | Cash, card, mobile money, bank transfer, and other tenders can be recorded. Direct authorization, settlement, webhook reconciliation, and terminal/mobile-money provider integration remain separate work. |
| Cashier control | Implemented | Role-based access, shift opening/closing, opening cash, expected cash, counted cash, refunds, returns, voids, and audit events are available. Automated shrinkage and exception alerts are not yet available. |
| Multi-branch operation | Implemented | Workspaces, branches, sections, staff memberships, and shared database reporting provide centralized operation. |
| Multi-checkout operation | Partial | Multiple staff sessions can trade against the same section and database. A first-class register/device identity and per-register drawer reconciliation are not yet modeled. |
| Offline operation | Partial | Idempotent queued order creation, line addition, and payment recording can replay after reconnection with catalog-version conflict checks. This does not authorize offline card or mobile-money transactions. |
| Receipt and cash-drawer support | Partial | Receipt/bill printing, printer configuration flags, and drawer-oriented shift controls exist. Native ESC/POS printing and physical drawer kick commands require a local hardware bridge. |
| Integrated weighing scale | Partial | Weight-based pricing and fractional quantities exist. Reading a physical scale over serial, USB, or a vendor protocol is not implemented. |
| Reporting | Implemented | Sales, section splits, finance posting, stock movement, shift, refund, and audit data are available. Grocery-specific margin, waste, sell-through, and cashier-exception dashboards need deeper treatment. |

## Highest-priority gaps

### 1. Batch, lot, and expiry control

Perishable stock needs receipt-level batch or lot records, manufacture and expiry dates, remaining quantity, and first-expiry-first-out allocation. Receiving should warn about short-dated stock; checkout should block expired stock; reports should show expiring and wasted inventory.

### 2. Customer and loyalty records

Add a shared customer profile with phone/email consent, loyalty account, points ledger, reward rules, redemption audit, and purchase history. Customer identity should work consistently across supermarket, restaurant, bar, lodging, events, and services.

### 3. Register and device identity

Introduce a register/workstation record tied to a section. Each shift, cash drawer, receipt sequence, offline queue, and payment terminal should identify the register. This enables per-lane reconciliation and safe multi-checkout reporting.

### 4. Exception and shrinkage controls

Add configurable alerts and review queues for repeated voids, manual price changes, excessive discounts, no-sale drawer openings, negative stock, unusual refunds, and till variances. Existing audit events provide source data but do not yet surface these patterns proactively.

### 5. Payment-provider reconciliation

Recorded mobile-money and card tenders should gain an external reference, provider status, webhook event log, settlement batch, fees, and mismatch workflow. Provider authorization must be idempotent and separate from recording an internal tender.

### 6. Hardware bridge

A small authenticated local service can translate browser requests into ESC/POS printing, cash-drawer pulses, customer-display output, and supported scale protocols. Hardware health and last-seen state should be visible to supervisors.

### 7. Rich retail pricing

Extend promotions with coupon codes, quantity breaks, buy-one-get-one rules, mix-and-match groups, member prices, scheduled markdowns, and explicit stacking rules. Every override should retain the rule and operator that produced it.

## Recommended delivery order

1. Add register/workstation identity and per-register shift reconciliation.
2. Add batch/expiry inventory with short-date and expired-stock controls.
3. Add customer and loyalty ledgers shared across every business sector.
4. Add payment references and provider reconciliation for mobile money and cards.
5. Add a supervisor exception dashboard and alert thresholds.
6. Build the optional local hardware bridge for printers, drawers, displays, and scales.
7. Expand retail promotions and add online order, pickup, and delivery workflows where the business needs them.

## Professional product references

- [Lightspeed purchase orders](https://retail-support.lightspeedhq.com/hc/en-us/articles/228840747-Creating-purchase-orders) show purchase orders organized by shop and vendor.
- [Lightspeed multi-location sales](https://retail-support.lightspeedhq.com/hc/en-us/articles/16524325094811-Managing-multi-location-sales) provides a useful benchmark for selling and fulfilling inventory across locations.
- [Square retail capabilities](https://squareup.com/us/en/retail/capabilities) provides a broad benchmark for inventory, checkout, customer, employee, and reporting workflows.
- [Square multi-store management](https://squareup.com/us/en/point-of-sale/features/multi-store?country_redirection=true) demonstrates centralized location, employee, and reporting controls.
- [Square offline payments](https://squareup.com/help/us/en/article/7777-process-card-payments-with-offline-mode) documents the risk limits and reconnection rules required for true offline payment authorization.
- [Square loyalty redemption](https://squareup.com/help/us/en/article/5347-how-customers-redeem-their-rewards) and [Lightspeed loyalty rewards](https://retail-support.lightspeedhq.com/hc/en-us/articles/360010942454-Creating-Loyalty-rewards) are reference points for earn-and-redeem workflows.

These references are product benchmarks, not claims that this platform integrates with those vendors.
