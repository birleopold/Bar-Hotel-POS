# Fizo complete face-by-face implementation roadmap

**Version:** 2026-10-23 · **Target branch:** `origin/main` only · **Status:** PLANNED (not implemented by writing this roadmap) · **Inventory base:** `d02d3768ed3df7e1ed4e9aacfe22c106eb8125d2`

## Non-negotiable engineering contract

1. Research operational workflows before implementation; adopt the simplest professional-grade sequence and confirm exceptions.
2. Work directly on `main`, push to `origin/main`, never create feature branches for this programme.
3. Supplied approved images are acceptance references: align proportion, spacing, color, typography, controls, responsive behavior and real data. Record per-template image baseline, viewport and measured discrepancy.
4. At most **two shared CSS foundations**, plus justified line-specific stylesheet(s). CSS ownership is exclusive; eliminate duplicate selectors, `!important` escalation, legacy imports and inline overrides before completion.
5. No patch-on-patch: trace failing flow to source; directly replace faulty selector, handler, template or service and delete superseded implementation in the same change after dependencies pass. No overlay-only fixes.
6. Every screen feature must exist from URL/permission through backend, state, template, interaction, validation, persistence, navigation, printing and tests; no mock/demo values in production.
7. Strong isolation for supermarket/grocery, restaurant, bar and hotel: tenant data boundaries, enabled capabilities, branded navigation and terminology; unrelated functionality must not leak.
8. Make sensible UX corrections without repeated confirmations; minimize clicks and reading and prioritize frequent tasks.
9. Preserve data, migrations, production integration behavior and existing working business flows; changes must be reversible through a safe deploy/rollback.
10. Run browser acceptance at desktop 1536×1024, laptop 1366×768, tablet 1024×768, mobile 390×844 and wide 1920×1080; both mouse/keyboard and touch; inspect reference pixel differences, text overflow, controls, focus, empty/loading/error states.
11. Every phase completion needs source-level tests, rendered checks, full navigation, permission/currency test and owner signoff against screenshot before marking complete.

## Cross-phase feature completion rule (24 October 2026)

When a problem in the current P00 verification phase concerns a feature also scheduled in another phase, **complete its directly related work in the same implementation package** instead of revisiting the same component later. Example: a hotel dashboard change includes its relevant P02 accessible shared components, P03 site/tenant authorization, P12 front-desk and housekeeping operations, P13 multi-module navigation, and P15 regression/viewport checks. For cashier changes, bundle relevant P01/P02/P03/P04/P05/P06/P07/P08/P09 checks. Unrelated workstreams remain independent.

This **does not bypass any acceptance gate or mark later phases complete**: record a cross-phase partial implementation with changed sources, permission/tenant/data checks, tests, viewport evidence, and unresolved requirements. Keep the phase order for unrelated work and overall signoff. Avoid duplicate template/controller/style ownership by completing all directly affected existing owners in the same change.

## Approved visual baseline

- **Supermarket management dashboard:** sidebar, branch/search/user top bar, greeting/banner/open POS CTA, four KPIs, setup checklist, quick actions, attention and recent activity, green/navy/white palette.
- **Supermarket cashier (two approved variants):** narrow left rail, store/cashier/register header with F3 search, broad image-product grid, top category tabs, fixed right basket with quantity buttons, prominently displayed UGX due and payment CTA, payment methods and hold/clear/print.
- **Tablet POS:** compact three-zone catalogue/basket/receipt layout only when applicable to the chosen business flow and available width.
- **Four-business unified visual:** common design language but independent supermarket, restaurant, bar, hotel dashboards and operative surfaces. No implementation is accepted merely because it resembles the image; it must work with real tenant data.
- **Reference files:** the five approved uploads from the conversation on 2026-10-23; store approved reference assets in repository design/reference after asset rights/provenance and filename approval. Until then use docs/FIZO_APPROVED_VISUAL_DESIGN_STANDARD.md and docs/FIZO_UNIFIED_UI_REFERENCE_2026-10-23.md.

## Execution phases (strict sequential gate, each with checkbox)

| Phase | Workstream | State | Exit gate |
|---|---|---|---|
| P00 | Discover and freeze baseline | In progress — [source inventory and CI baseline](evidence/p00-2026-10-23/README.md); browser baseline pending | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P01 | Architecture and CSS clean replacement | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P02 | Shared components and mobile responsiveness | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P03 | Tenant setup and true isolation | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P04 | Authentication and register identity | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P05 | Supermarket dashboard and management | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P06 | Supermarket cashier pixel-parity | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P07 | Retail transaction correctness | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P08 | Retail catalogue and stock | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P09 | Retail buying, employees, reports | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P10 | Restaurant front of house | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P11 | Bar operations | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P12 | Hotel and lodging | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P13 | Mixed capabilities and optional modules | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P14 | Platform billing/admin and compliance | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |
| P15 | Full route-by-route QA, visual acceptance, deployment | ☐ Not started / unverified | Changes reviewed, all relevant screens and workflows tested, visual and tenant acceptance |


### P00 — Discover and freeze baseline

Inventory routes, templates, includes, CSS, JS, API views, model writes, events, permission checks, responsive breakpoints and current screenshots. Build route-to-template-to-CSS-to-controller crosswalk; mark dead/duplicate files, gather pixel baselines. No deletions before reference and dependency analysis.

Checkpoint: source `8d45fb3` has 636 resolved URL patterns, 156 tracked templates, 28 visual candidates needing dynamic tracing and eight missing stylesheet references. Exact-source CI has 83 failing tests. See the linked P00 evidence; no phase completion or production verification is implied.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P01 — Architecture and CSS clean replacement

Enforce at most two global foundations: design-tokens.css and application-shell.css (existing fizo-fresh.css/fizo-console-shell.css can be canonical owners instead of new files). Business surface CSS only where truly distinct: retail-cashier, retail-management, hospitality, hotel-frontdesk, platform/setup, auth, printing. Merge stock/purchasing/management into coherent owner as appropriate. Delete old stylesheet only after removal of all references, exact replacement and regression validation.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P02 — Shared components and mobile responsiveness

Single canonical buttons, inputs, tables, cards, dialogs, sidebars, toasts, badges, skeletons, empty/error states, keyboard focus, screen reader behavior, printer styles; desktop/tablet/mobile/wide-screen and touch target contracts.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P03 — Tenant setup and true isolation

Tenant-aware routing, setup feature flags, module/role/permission checks enforced server side, outlet scoping, currency/timezone branding, independent menu/navigation, no hotel table artifacts on supermarket screens; tenant data access tests.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P04 — Authentication and register identity

User/password or selectable initials + PIN per configured service, lockout, invitation, recovery, assignment, safe idle behavior: retail assigned cashier should not reauthenticate frequently; restaurant/bar/hotel shared terminals auto-lock appropriately.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P05 — Supermarket dashboard and management

Match management approved reference; real UGX metrics, setup checklist, inventory/staff/purchasing quick actions, alert and activity drilldowns, branch switcher; responsive and no demo values.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P06 — Supermarket cashier pixel-parity

Match two cashier approved screenshots: header and F3 search, side nav, categories, four/five responsive product columns, image card scale, fixed basket panel, whole-item quantity, measured item fractions by unit, prominent UGX total, payment options, receipt, hold/clear/print, cashier identity, register state, customer-facing display.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P07 — Retail transaction correctness

Fast barcode scans and search; add once without unexpected refresh; product variant/UOM, offers/tax, no duplicate submission, payment cash/card/mobile money including settlement callbacks, change, void, return/refund, held/offline queue idempotency and receipts.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P08 — Retail catalogue and stock

Products, import, category, SKU/barcode, media, price lists, variants, opening stock, reorder thresholds, batches, expiration, count, transfer, receive, write-offs, scale labels, supplier links, auditable inventory ledger.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P09 — Retail buying, employees, reports

Purchasing requisition/order/receive/bills, staff setup, register shifts, cash reconciliation, all daily/monthly/export reports and owner drilldown, permissions.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P10 — Restaurant front of house

Distinct restaurant dashboard, table/floor plan, seat/guest, dine-in/takeaway, menu/modifiers/course, fire to kitchen, KDS acknowledgement and bump, split bills and combined payments, tips and service charge, receipt.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P11 — Bar operations

Bar dashboard, standalone quick sales or long-lived tab, pours/measurements, rounds, transfers, bartender shift, split tab, account settlement, discounts with approvals, stock deduction, receipt and bartender handoff.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P12 — Hotel and lodging

Hotel-specific dashboard, inventory/calendar/tape chart, rate plans and room types, availability conflict prevention, reservations, deposit, check-in, folios and payments, housekeeping, out-of-service rooms, checkout, night audit, reports.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P13 — Mixed capabilities and optional modules

Feature entitlement matrix for retail + restaurant/bar/hotel combinations: selected functions integrate cleanly but never inject irrelevant controls or alternate shells. Event bookings, room charges, customer account, loyalty and other enabled add-ons only.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P14 — Platform billing/admin and compliance

Platform tenant management, business white label, organization setup, subscription/license, audit, Uganda payments/tax/EFRIS if supported/approved, privacy, exports, backup and restore, secure integration credential handling.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.

### P15 — Full route-by-route QA, visual acceptance, deployment

For every registered GET and POST route: navigate, screenshot compare to approved baseline, confirm actionable control, no 500, permission/tenant safety, correct currency, responsive sizes, tablet hardware, offline and printer flows. Visual diff thresholds with reviewed exceptions; Django/test/static build/lint/CI; commit to main, push, deploy and verify live health and end-to-end scenarios.

**Required artifacts:** exact changed-file list; routes/screens impacted; CSS owner and removed selectors; screenshots side-by-side; migration/data-safety note; real-browser pass; automated tests; push SHA; verified production outcome. No phase marked done without evidence.


## Screen-family acceptance ownership

### Platform, tenant provisioning and organization console

**Template family:** `backend/apps/console/templates/`

**End-to-end owner:** Organization signup, plan, site, outlet, profile, module entitlement, setup and platform owner flows.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Public account and authentication

**Template family:** `backend/templates/`

**End-to-end owner:** Signup, password reset, login, staff invitation, approval, PIN and account recovery.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Staff shell, dashboards and common pages

**Template family:** `backend/apps/staff/templates/staff/`

**End-to-end owner:** Navigation, search, owner overview, daily management, settings, notifications, help and role-aware actions.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Retail cashier and sales

**Template family:** `backend/apps/staff/templates/staff/`

**End-to-end owner:** Register assignment, checkout, basket, price, promotion, hold/resume, customer display, shifts, receipt, return/refund, offline recovery.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Stock and inventory

**Template family:** `backend/apps/staff/templates/staff/inventory/`

**End-to-end owner:** Balances, receipts, stock counts, batch/expiry, transfer, shelf, scales, movements and reconciliations.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Purchases and suppliers

**Template family:** `backend/apps/staff/templates/staff/purchasing/`

**End-to-end owner:** Supplier records, purchase orders, receiving, payable reconciliation and returns.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Restaurant and bar table/order and KDS

**Template family:** `backend/apps/staff/templates/staff/kds/`

**End-to-end owner:** Dining tables, tabs, order rounds, modifiers, kitchen tickets, split/transfer, settle, service display.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Hotel front desk and lodging

**Template family:** `backend/apps/staff/templates/staff/lodging/`

**End-to-end owner:** Availability, rates, bookings, check-in/out, room status, folio, housekeeping, maintenance and night audit.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Events and booking

**Template family:** `backend/apps/staff/templates/staff/events/`

**End-to-end owner:** Spaces, event calendar, booking lifecycle, deposits, services, conflict detection.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Finance and reporting

**Template family:** `backend/apps/staff/templates/staff/finance/`

**End-to-end owner:** Expense/cashbook records, shift reconciliation, owner metrics and drilldown.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Customers and loyalty

**Template family:** `backend/apps/staff/templates/staff/customers/`

**End-to-end owner:** Optional retail identity, guest identity, customer data permissions and history.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.

### Settings, staff and integrations

**Template family:** `backend/apps/staff/templates/staff/settings/`

**End-to-end owner:** Member permissions, workstation, branding, integration, EFRIS configuration, security audit.

**Per-face checks:** correct header/sidebar/CTA, relevant filters, forms, list/detail/edit/delete, confirmation/undo, validation, empty/error/loading, pagination and export where relevant; every visible button is wired to a permission-safe endpoint; linked CSS and JS have one canonical owner. Business-specific terms and visual references verified.


## Mandatory CSS audit and disposition register

Each stylesheet below must be classified **keep as canonical / merge into shared foundation / keep as business-specific / delete after replacement**. Default state is **pending trace**; do not assume an unused name means safe to delete.

| File | Required audit | Status |
|---|---|---|
| `backend/apps/staff/static/staff/fizo-auth-2026.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-console-shell.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-fresh.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-hospitality-floor.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-hotel-frontdesk.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-inventory-workflows.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-purchasing.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-register.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-setup-area.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-setup-wizard.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/fizo-stock.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/grocery-checkout.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/grocery-owner-console.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/hospitality-console.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/hospitality-workflows.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/management-workflows.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/retail-cashier.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/retail-workflows.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/staff-kds-operations.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |
| `backend/apps/staff/static/staff/staff-workbench.css` | Find every import/link/selector owner, overlap and cascade specificity; map referenced HTML/JS; consolidate or replace, then eliminate stale references | ☐ Pending |


## Exhaustive template audit register (156 tracked HTML files)

For **every** HTML entry: record named URL, base/inclusion chain, line-of-business exposure, feature flag, JS handler, CSS ownership, GET/POST handlers, model/service, permissions, expected empty/loading/errors, approved comparison screenshot(s) and responsive checks. Including a file here does **not** mean it has passed.

| Template file | Visual/function audit | Status |
|---|---|---|
| `backend/apps/console/templates/console/base.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/includes/fizo_nav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/includes/fizo_sidebar.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/includes/nav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/includes/sidebar.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/index.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/catalog_import.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_category_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_category_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_outlet_confirm_delete.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_outlet_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_outlet_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_recipe_confirm_delete.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_recipe_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/menu_item_recipe_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/modifier_group_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/modifier_group_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/modifier_option_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/modifier_option_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/outlet_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/outlet_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/overview.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/practice_sale.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_rate_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_rate_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_type_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/room_type_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/service_offering_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/service_offering_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/service_offering_option_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/service_offering_option_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/setup_wizard.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/site_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/org/site_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/plan_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/plan_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/tenant_control_plane.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/tenant_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/console/templates/console/platform/tenant_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/base.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/business_date.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/customers/detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/customers/form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/customers/list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/dashboard.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/booking_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/booking_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/bookings_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/calendar_week.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/space_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/events/spaces_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/finance/category_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/finance/entries_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/finance/entry_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/documentary_photo.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/empty_state.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/exception_assessment_fields.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/fizo_pos_catalogue.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/fizo_retail_sales_landing.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/form_errors_block.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/grocery_owner_dashboard.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/messages.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/nav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/orders_lanes.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/service_tv_ticket.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/sidebar.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/includes/workspace_subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/balances.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/batches.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/count_create.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/count_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/counts_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/intelligence.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/movement_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/movement_upload.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/movements.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/scale_labels.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/shelves.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/transfer_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/inventory/transfer_receipts.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/kds/queue.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/availability.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/folio_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/folios_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/housekeeping.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/maintenance.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/night_audit.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/reservation_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/reservation_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/reservations_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/room_types_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/rooms_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/lodging/tape_chart.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/login.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/management.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/management_shift.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/management_source.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/menu_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/notifications/inbox.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/order_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/order_detail_supermarket.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/order_print.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/orders_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pending_approval.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pin_setup.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos/customer_display.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos/offline_queue.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos/pickups.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos/wholesale_pricing.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/pos_shifts.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/promotion_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/promotion_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/promotions_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/purchase_order_create.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/purchase_order_detail.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/purchase_orders_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/supplier_balances.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/supplier_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/purchasing/suppliers_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/retail_pos_start.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/sales_summary.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/search/index.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/search/palette.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/service_tv.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/audit_log.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/branding.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/efris_settings.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/includes/subnav.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/integration_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/integrations_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/invite_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/invites_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/member_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/members_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/modules.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/owner_reports.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/settings/worker_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/table_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/tables_list.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/terminal.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/workstation_form.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/workstation_pair.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/workstation_test.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/apps/staff/templates/staff/workstations.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/templates/includes/phase4_control_panel.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/templates/password_reset/confirm.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/templates/password_reset/request.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |
| `backend/templates/public/signup.html` | Route, linked assets, interaction, persistence, isolation, pixel match, mobile and accessibility | ☐ Pending |


## JavaScript / route owner inventory

**JavaScript sources (5):**
- [ ] `backend/apps/staff/static/staff/grocery-checkout.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.
- [ ] `backend/apps/staff/static/staff/retail-counter-v2.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.
- [ ] `backend/apps/staff/static/staff/staff-command.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.
- [ ] `backend/apps/staff/static/staff/staff-density.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.
- [ ] `backend/apps/staff/static/staff/staff-kds-live.js` — map each event listener, search/scanner handler, update and network call; eliminate duplicate controller authority; test happy/error/retry cases.

**URL inventories:**
- [ ] `backend/apps/api/urls.py` — enumerate named paths, permissions, request methods, mapped template and API dependencies.
- [ ] `backend/apps/console/urls.py` — enumerate named paths, permissions, request methods, mapped template and API dependencies.
- [ ] `backend/apps/staff/urls.py` — enumerate named paths, permissions, request methods, mapped template and API dependencies.
- [ ] `backend/config/urls.py` — enumerate named paths, permissions, request methods, mapped template and API dependencies.

**Backend dependency discovery:** map `backend/apps/*/` models, service modules, view functions, tasks, payments, signals, authorization, migrations and integration handlers to a face/flow. Backend-only modules are not ignored: security and correctness must be covered even without visible UI.

## Workflow definitions and evidence of completion

| Business | Primary happy path | Necessary exceptional paths |
|---|---|---|
| Supermarket | Assigned cashier → open register → barcode/search → instant basket → payment → receipt → next sale | Unrecognized barcode, measured goods, out-of-stock policy, duplicate scan/submit, hold/resume, refund, offline queue, printer failure, closing balance |
| Restaurant | Shift → floor/table → items/modifiers → kitchen → serve → split/pay → close table | Transfer table, void approval, round sequencing, printer/KDS outage, split by seat, partial payment |
| Bar | Bartender PIN → new tab/quick sale → drinks/rounds → settle/transfer → shift close | Running tab, suspended tab, cash/card/money split, wastage, overpour/stock, return and manager override |
| Hotel | Availability → quote/rate → reserve → assign room → check in → post folio → housekeeping → pay/check out → night audit | Date collision, out-of-service room, change room/rate, deposit and refund, late/early stays, partial folio and reversal |
| Platform | Signup → business choice/modules → branch/register/staff/product/room/menu setup → test transaction → activate | Module downgrade, out-of-entitlement route, tenant crossover, broken setup step, password/PIN recovery, currency mismatch |

## Exact implementation procedure for each face/defect

1. Capture current UI and approved target, including exact viewport and state.
2. Trace actual route → view → template + includes → CSS and JS → persistence; write one root-cause statement.
3. Identify canonical component and stylesheet owner, then modify original owner in place; remove old selector/controller/template code, not override it from another layer.
4. Cover all server behavior including failure, permissions, money formatting, rounding, race conditions and transactions.
5. Test keyboard, touchscreen, scanner, printer, accessibility and different sizes. Compare target pixel geometry; iterate in same canonical owner.
6. Search repository for stale imports, selectors, duplicate listeners and old functions; delete only with proof that no live route depends on them.
7. Run focused and cross-business regression, then push direct `main` commit. Attach SHA and browser/CI evidence; update the corresponding row to completed **only after** release verification.

## Technical acceptance gates

- **CSS:** one or two shared foundations only, no unowned selector overlap; no blanket `!important`, dead files removed, no inline style-as-patch and no double-loaded assets; verified browser computed styles.
- **Data:** currency comes from tenant setup (UGX for Fizo Tech), monetary arithmetic uses Decimal, payment retries idempotent, stock changes traceable, shift/customer identity and tenant scope correct.
- **Business boundaries:** server blocks unauthorized line-specific routes and API methods; screen hides unavailable modules; retail needs no table/guest name; mixed entitlements show only enabled features.
- **Operational quality:** no random refresh while adding items, whole quantities for unit items, fractional quantities only for configured measures, one working search/scanner controller, real register identity, accessible receipt and customer display, quick return to next sale.
- **QA:** view/layout screenshot diffs for all templates, Django checks, migrations check, static compilation, tests, CI, live smoke flows on Fizo tenant and independent hotel/restaurant/bar tenants; a browser screenshot is required for any pixel-perfect claim.

## Progress accounting

Maintain one row per phase and one per template/CSS file. Use states `not started`, `in progress`, `implemented awaiting browser validation`, `verified on staging`, `verified in production`. Count only production-verified items in completion percentage. Record defects with root cause, canonical replacement, removed files/functions, and evidence; do not relabel source code written as feature done.

## Research anchors

- Oracle Simphony transaction and KDS operations: https://docs.oracle.com/en/industries/food-beverage/simphony/
- Oracle Simphony staff/check/order flow: https://docs.oracle.com/cd/E76065_01/doc.29/e69878/
- Cloudbeds PMS daily hotel workflow: https://myfrontdesk.cloudbeds.com/hc/en-us/articles/40771665486363-Your-Cloudbeds-PMS-Daily-Operations-Guide
- Existing repository: docs/FIZO_POS_EIGHT_PRODUCT_BENCHMARK_2026-10-22.md, docs/FIZO_FULL_ROUTE_TEMPLATE_MASTER_2026-10-22.md, docs/FIZO_ROUTE_VERIFICATION_REGISTER_2026-10-22.md and line-specific acceptance registers.

**Authority:** This document is the umbrella implementation contract. Existing acceptance registers provide details, but no earlier checklist can waive the canonical-owner, full-route, isolation, visual-parity or no-patching rules above.
