# Fizo approved interface — mandatory visual standard

The user-approved visual reference is **Unified POS Experience Across Industries**, supplied again on 2026-10-22. Use the actual user-provided image in the design conversation for visual comparisons. This document describes the reference; it is not a substitute for actual screenshot inspection.

## Core appearance
- Bright white/light-grey background, restrained cards, crisp thin borders, and green (#00884b range) primary calls to action. Dark navy heading/body text. **No gradients or generic oversized hero banners.**
- Persistent, compact left sidebar with clear icons, short labels and one green selected navigation state.
- Small, concise content headers; information is accessible without excessive vertical scrolling.
- Dense but legible transaction registers, status indicators, helpful empty states and real data only (never fabricated KPIs).
- Touch-friendly responsive operation on desktop, laptop, tablet and mobile. When the window narrows, tables can scroll, but checkout controls remain reachable.
- Consistent Fizo brand, icon treatment, spacing and button shapes; business-specific content must not change the overall design language.

## Business-specific layouts visible in reference
- **Supermarket:** dashboard metrics, sales visual, top products; cashier product-grid + persistent current basket, search/barcode, categories, payments; compact product management list and inventory pages. Walk-in checkout must not require customer identity.
- **Restaurant:** occupied/available table floor, dine-in orders, menu, kitchen; item-grid + live current order, kitchen submission and bills.
- **Bar:** tab-first order management, drinks categories, running order and checkout.
- **Hotel:** availability/reservations, occupied/cleaning/maintenance rooms, guest folio/night audit/housekeeping, room management.

## Per-page acceptance requirements
Inspect and replace **the actual rendered page structure**, not just colors on legacy CSS. Confirm correct role, selected site/outlet (including multi-site and all-sections cases), route, keyboard/tablet/mobile layout, form errors, data correctness, empty state and working actions. Browser screenshot compare with user reference and deployed revision before marking DONE. Git commits and source tests alone are NOT verified completion.

## Implementation safeguard
When designing a shared view, keep supermarket/retail, restaurant/bar and hotel branches independent. Preserve transactional business logic and authorization. Never make all business lines render the same screen simply because their CSS is shared. All product management, checkout, purchasing, counts, stock movement, reports and setup routes used by a supermarket must be individually audited.
