# F6 supermarket-specific software and field acceptance

**Checkpoint: 18 October 2026** — This is a release gate, not evidence that physical hardware was tested.

## Implemented user journeys

| Task | Where staff find it | Safety behavior |
| --- | --- | --- |
| Anonymous quick grocery sale and scanner input | Retail orders and fast checkout | No customer profile, table or hotel required |
| Shelf location lookup | Inventory → Shelf locator | Warehouse address label, not a separate stock balance |
| Weighed 20–29 EAN-13 barcode setup | Inventory → Scale labels | Explicit approved format per product, checksum and tenant scope |
| Offline reconciliation and cash ceiling | POS → Offline queue | Cash only; unverified card or mobile money cannot be paid offline; limit owner-controlled |
| Wholesale quantity tiers | Retail order → Wholesale prices | Manager + identified customer; price snapshotted and eligibility recomputed on quantity changes |
| Customer display | Retail order → Open customer display on second screen | Staff session, read-only, no contact, public URL inaccessible; browser refresh |
| Non-cash loyalty reward | Customer profile → Redeem a non-cash reward | Approved positive points balance, idempotent, no value converted into UGX |
| Fully paid pickup | Paid retail order → Schedule pickup; POS → Pickups | Only fully paid sale linked to customer, manager schedule and verified handover, no duplicate stock reduction |

## Mandatory release gate for each physical site

- [ ] On a real PostgreSQL tenant, repeat two simultaneous sales, stock reservation/lot transactions, supplier transfers and two overlapping refund/credit actions. Verify nonnegative inventory and row-level tenant/outlet isolation.
- [ ] Demonstrate anonymous sale, held basket, same barcode twice, missing PLU, weighted scan, cash tender/change, split cash+mobile money verification, receipt reprint and next customer across Windows desktop, Firefox, Android and iPhone Safari.
- [ ] Verify responsive screens and keyboard scanning, 200% and 400% zoom, labels/focus, screen-reader headings, error announcements and WCAG 2.2 touch target minimums.
- [ ] Independently inspect actual scanner, optional label-printer, weighing scale, customer monitor, cash drawer and USB/network printer with model/firmware notes and operator-signed pass/fail. Browser print is not direct hardware control, and weighed barcodes are not certified scales.
- [ ] Simulate offline loss/reconnection with duplicate payment retries, limits changed by owner, rejected electronic settlement, expired catalog and a conflicting multi-till operation.
- [ ] Review URA EFRIS setup, actual supplier invoices and Uganda-specific tax receipt rules with a qualified local implementer and the registered merchant. Do not infer tax status from code alone.
- [ ] Restore a real database backup in staging; practice deployment rollback; obtain signed store manager/cashier acceptance.

## Not safe to enable until implemented

- **Customer credit (SM-23):** must have per-customer credit approval and limits, receivable ledger, aging, collections, reversals and bad-debt process without posting loaned/deferred revenue as cash. Existing lodging folios are not a retail credit account.
- **Unpaid layaway (SM-24):** must reserve tracked batches/units atomically, store deposits as liabilities until earned, safely refund/cancel and release reservation under concurrency. Existing held baskets and fully paid pickups are not unpaid layaway.
- **B2B quote conversion, monetary loyalty redemption and coupons:** need tax/discount accounting, precedence and an explicit tenant-agreed cash valuation. Do not automatically convert points into currency.
- **Publicly paired customer display and queue calls:** second-screen currently uses the authenticated cashier session; public pairing is not available.
- **Release certification:** do not mark any physical/external gate green from GitHub CI or source code.

## Evidence and references

- Existing implementation roadmap: `docs/SUPERMARKET_FAST_TRACK.md` and `docs/SUPERMARKET_IMPLEMENTATION_CHECKLIST.md`.
- Automated CI: GitHub Actions workflow on the exact main SHA; record the SHA, count and exclusions before reporting green.
- Operational reference: [Shopify POS partial payments](https://help.shopify.com/en/manual/sell-in-person/shopify-pos/payment-management/multiple-partial-payments), [Shopify POS store credit](https://help.shopify.com/en/manual/sell-in-person/shopify-pos/payment-management/store-credit), [Odoo 19 price lists](https://www.odoo.com/documentation/19.0/applications/websites/ecommerce/configuration/prices.html), [WCAG 2.2](https://www.w3.org/TR/WCAG22/).

**Pass meaning:** Release-ready only when software tests AND each necessary site acceptance item have evidence. If a feature is disabled and explicitly excluded, label the exclusion in the merchant agreement and do not promise it as part of the delivered F6 scope.
