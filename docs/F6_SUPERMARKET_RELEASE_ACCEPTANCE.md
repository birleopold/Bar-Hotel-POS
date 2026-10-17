# F6 field and release acceptance: evidence still required

This is a test protocol, **not a record that physical tests passed**. Use a disposable/staging tenant and sample products only. Do not run tests on live cash, customers or stock without a reviewed plan. Mark each observation with device, browser/OS, time, staff role, outlet and source commit.

## Supported code paths now available
- Inventory → Aisles & shelves: search name, SKU, barcode, aisle, shelf and bin; update labels without altering stock.
- Inventory → Scale labels: administrator opt-in to **one exact** net-grams EAN-13 format. Every label must use a locally verified prefix and five-digit product code, five net-weight digits, and valid EAN checksum. Real equipment may use different layouts.
- POS → Offline device queue: review failed replays, original IDs, stale catalog, and owner-only cash payment ceiling. Card/mobile-money settlement is not asserted when offline.
- Management → Reports: register/tender attribution added in F5; do not infer F5 is finished from this screen.

## Physical scale + scanner (unverified)
- [ ] Read local manufacturer/model, published protocol and label examples. Confirm prefix, product digits, grams and the actual checksum and weight handling (net vs gross, tare, decimals).
- [ ] Test scanned 1.250 kg label against **price per kg**, line discount, tax, actual stock decrement on paid sale and thermal receipt.
- [ ] Test invalid checksum, a label with zero grams, an unconfigured prefix, duplicate product mapping, wrong outlet, and quantity changed from 1; no sale or stock posting on rejection.
- [ ] Print labels of 0.001 kg and 99.999 kg only if your physical scale supports them. Document support limits and reject unsupported formats.
- [ ] Confirm a non-scale EAN/UPC barcode remains a normal lookup.
- [ ] Tare calibration, zeroing, price-embedded layouts and legally certified weighing are **not implemented**.

## Offline cash and reconciliation (unverified)
- [ ] Configure an owner-approved per-transaction cash limit and record the currency/ceiling; check limit editing rejects non-admin and shared PIN-only sessions.
- [ ] Disconnect a cashier device after a catalog download, capture a cash transaction within the policy, and reconnect. Verify the original request ID reaches exactly one order/payment and stock movement.
- [ ] Queue a cash amount above the limit and cross-currency payment; confirm neither posts money, and manager review cannot silently settle it.
- [ ] Confirm stale prices and mismatched catalog versions create visible conflicts, not stale-charge application.
- [ ] Simulate device reboot, browser crash and storage eviction; recover or reconcile pending local cash receipts manually. **No durable device-side offline cache is certified by these server APIs alone.**
- [ ] Confirm card/mobile money/bank cannot be declared settled by offline replay.

## Picking, roles and multi-device (unverified)
- [ ] With a restricted storekeeper, edit own-outlet shelf label; deny edits to another outlet or another tenant.
- [ ] Cross-check same SKU in separate branches has separate shelf labels; inventory quantity remains unchanged.
- [ ] On 320 px phone, tablet portrait/landscape, laptop and large touch terminal, verify pagination, search, focus order, visible errors and form labels, 24px minimum targets or spacing per WCAG 2.2.
- [ ] Test Firefox, Chrome, Safari and actual barcode scanner keyboard wedge, receipt printer and touch keyboard.
- [ ] Perform PostgreSQL concurrent transactions, RLS/permission probes, backup/restore and rollback drills before production certification.

## Unimplemented optional workflows — no sign-off
- [ ] SM-22 consent, redeemable rewards/points liability and reversal.
- [ ] SM-23 authorized customer credit, aging, collections and write-offs.
- [ ] SM-24 layaway/deposit/stock reservation, cancellation and pickup.
- [ ] SM-25 wholesale accounts, tier prices, invoicing and quote conversion.
- [ ] SM-28 secure paired customer-facing display and no guest data leakage.
- [ ] SM-35 suspicious void/refund/price override and shrink drill-down reporting.

## Reporting rule
Only mark CI green when its run head matches current `origin/main`. Keep software tests, PostgreSQL, browser, physical hardware/provider, VAT/EFRIS, deployment and backup/restore as separate evidence categories.
