# Unified Fizo visual acceptance reference (2026-10-23)

Reference supplied by the owner: **Unified POS Experience Across Industries(8).png** (1536 × 1024).

## Design source of truth
The four columns in the reference show supermarket, restaurant, bar, and hotel. Each column has four comparable horizontal sections: dashboard, transaction workspace, catalogue/management, and key business features. The shared visual system includes a pale gray-green canvas, white softly rounded panels, narrow separators, green active navigation and primary actions, compact dark headings, and subtle iconography.

### Global invariants
- Preserve the Fizo identity, compact left navigation, consistent green accents and neutral backgrounds.
- All 4 business lines must have coherent dashboards with KPI cards and actionable, meaningful data.
- Each line has its own transaction workspace, not one generic checkout: supermarket product-grid/basket/pay; restaurant tables/ordering/kitchen; bar tabs/drinks/settlement; hotel reservations/rooms/availability.
- Catalogue/management pages use consistent table density, search, filters, status chips, and action placement.
- Use the tenant's configured currency, not the USD prices drawn in the *illustrative* reference image.
- Preserve real data, permissions, barcode/search, totals and payment behavior. The screenshot is a visual reference, not a specification for replacing functional components.
- Desktop, tablet and phone should share the visual language while stacking layouts at appropriate breakpoints; the four-column composite itself is not the expected end-user screen.

### Stylesheet ownership
- `fizo-fresh.css`: shared tokens, navigation, cards, controls, tables, common responsiveness.
- `retail-cashier.css`: supermarket cashier-specific composition (legacy base and approved overrides combined in original cascade order).
- `retail-counter-v2.css` and `fizo-retail-sales.css`: retail workflow-specific styles, pending dependency-aware review and convergence.
- `hospitality-workflows.css`: restaurant/bar ordering composition, migrated from `fizo-hospitality-pos.css`, with existing styling preserved; further specialization and visual comparisons pending.
- Hotel-specific styles must remain separately scoped until room/reservation screens are compared and verified.

### Required acceptance before declaring pixel parity
1. Capture actual screenshots at the same viewport size for each of the 12 reference panels (four businesses × dashboard/order/management).
2. Compare navigation, geometry, type scale, color, control alignment, panel sizing, whitespace, icons, empty states, and mobile breakpoints.
3. Verify live workflows and permissions across the four business lines.
4. Remove duplicate CSS selectors and obsolete files only after checking imports and templates; do not delete styling merely because its filename is old.
5. Re-run Django tests, static collection and live browser visual checks before production rollout.

## Implementation status
- [x] Combine two cashier CSS files while preserving cascade order, update template/tests and delete those superseded files.
- [x] Normalize shared green active-nav, common cards, controls and tables in `fizo-fresh.css`.
- [ ] Audit all CSS dependencies and deduplicate across remaining business lines (retail counter and sales-start consolidated into `retail-workflows.css`; restaurant/bar/hotel work remains).
- [ ] Build and validate distinct restaurant, bar, hotel panels against approved reference.
- [ ] Capture and compare actual browser screenshots pixel by pixel.
- [x] Add repository regression tests for consolidated retail stylesheet references (`test_unified_css_architecture.py`); execution pending.
- [ ] Run test suite, confirm production deploy and check all supported breakpoints.

**Caution:** A reference image alone is insufficient evidence of pixel-perfect parity. No browser screenshot or deployment verification is claimed by this document.
