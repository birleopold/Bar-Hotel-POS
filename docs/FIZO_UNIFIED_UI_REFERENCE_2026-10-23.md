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

## CSS cleanup verification update — 2026-10-23
- Eight retired stylesheets from the retail, dashboard, and management consolidation passes are expected to be absent.
- A repository-level test now checks literal Django `{% static 'staff/…css' %}` links in **all staff templates**, rather than only the few known pages. This detects broken links when executed against the checkout.
- The test also checks retired management stylesheet names in templates.
- **Not yet verified:** full application CSS inventory outside `backend/apps/staff`, dynamically generated stylesheet URLs, CSS `@import` chains, test execution in a Django environment, live screenshots, and hotel reservation template dependency mapping.
- Do not delete more files without tracing their consumers and running integration tests; a reduction in filenames alone is not proof of visual equivalence.

## Visual component adoption — 2026-10-23
- [x] Dashboard template now uses the common `fz-industry-dashboard`, `fz-page-heading`, `fz-kpi-grid`, `fz-kpi`, and `fz-dashboard-panels` classes with existing bound KPI values preserved.
- [x] Retail product management now uses shared heading, toolbar, and table component classes; hospitality menu uses the shared management page heading scope.
- [x] Regression tests assert the actual template integration and dynamic sales/product values remain bound.
- [ ] Compare screenshot against approved reference at target viewport; still blocked by unauthenticated browser profile.
- [ ] Confirm responsive regressions, style precedence, and automated tests in a full repo checkout.
- [ ] Finish bar, restaurant and hotel management/transaction screen parity; common class adoption does not mean pixel-perfect rendering.


## Platform-owner shell recovery — 2026-10-28
- The central platform at `pos.leosoftug.com` is platform-neutral and must never inherit a tenant name, logo, color identity, or selected workspace merely because a stale tenant session exists.
- Root cause of the October regression: the neutral Console sidebar/top-bar templates still rendered retired `.staff-sidebar__*` and `.wb-*` class contracts after the shared fresh stylesheet had moved to the `.fz-*` shell. Content panels therefore remained styled while navigation collapsed into raw links/lists.
- The obsolete platform/Console shell markup has been replaced with the current `.fz-brand`, `.fz-scope`, `.fz-nav`, `.fz-top-*` and shared button/table/card primitives. No compatibility stylesheet was added.
- Platform-wide routes now suppress the tenant selector when there is no explicit tenant context. A platform operator sees **Platform administration**, Workspaces, Plans, Console home and their operator identity—not the first tenant in the database.
- Workspaces, Plans, workspace/plan forms and the tenant control plane now share the same neutral platform component layer in `fizo-fresh.css`; the Workspaces page inline CSS was removed.
- The tenant control plane is organized as a responsive two-column management grid with table-heavy/domain/history sections spanning the full width. Existing forms, permissions, audit behavior and POST endpoints remain unchanged.
- The shared stylesheet URL is version-bumped so browsers do not retain the broken shell after deployment.
- Regression tests now assert the fresh shell contract, platform neutrality under a stale tenant session, absence of retired shell classes, absence of inline Workspaces CSS, and consistent platform component use across Workspaces, Plans, create/edit forms and tenant control plane.
- This recovery does **not** claim screenshot parity until the deployed central host is captured and compared after static collection/deployment.
