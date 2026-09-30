> Current execution status: see [Full suite implementation checklist](SUITE_IMPLEMENTATION_TODO.md) and [code audit](CODE_AUDIT_2026-09-29.md). This March product vision is historical; its phase table is not a current release certificate. Shared-terminal PINs, modifiers, linked retail returns, supplier settlement and charge-to-room have since shipped. Named workstation configuration and device-linked shifts are the next implementation checkpoint. Device hardware labels do not imply working printer drivers or multi-till cash attribution.

# Hospitality Multi-Tenant SaaS — Product Plan

This document describes the vision, feature set, technical direction, UI principles, and roadmap for a unified **hospitality and retail operations** platform—**hotels, restaurants, bars, cafés, lodges**, plus **supermarkets, retail shops, and convenience / general merchandise POS**—sold as **software as a service**. The active codebase is the **Django** app in **`backend/`**; this plan extends that foundation toward full multi-tenancy, white-label branding, and operational simplicity for non-technical staff.

---

## 1. Vision

Deliver **one coherent product** where each subscribing organization gets:

- A **branded workspace** (logo, colors, naming, receipts) without engineering effort.
- **Multiple physical sites** (properties) and **outlets** per site (e.g. main restaurant, pool bar, lobby café, lodge check-in, **mini-mart, supermarket floor, boutique retail**).
- **Role-based access** so floor staff see only what they need—large touch targets, short flows—while owners and managers get reporting and configuration.

**Design principle:** Users choose **what they are doing** (“Take payment”, “Check in guest”, “Count stock”), not abstract module names. The application routes them by **role**, **outlet**, and **permissions**.

---

## 2. Target Users

| Persona | Needs |
|--------|--------|
| **Owner / GM** | Cross-outlet performance, branding, billing, user management |
| **Manager** | Scheduling, approvals, discounts, inventory thresholds, local reports |
| **Front desk / lodge host** | Reservations, check-in/out, room status, guest folio |
| **Server / bartender** | Fast POS, tables/tabs, modifiers, split bills |
| **Kitchen / bar back** | Order queue (KDS optional), prep status |
| **Storekeeper** | Receiving, transfers, waste, stock counts |
| **Accountant (read-only)** | Exports, audit trail, reconciliation-friendly views |

---

## 3. UI & Brand Direction

The interface should feel **warm, clean, and human**—inspired by the following creative direction:

- **Warm lighting:** Bright, hazy, warm aesthetic—like strong but soft daylight. Use warm off-whites, sand, or soft peach bases; gentle gradients (e.g. sunrise); diffuse shadows; avoid stark clinical white and razor-sharp borders everywhere.
- **Vibrant community colors:** Energetic accent palette (coral, turquoise, citrus, magenta) on a restrained warm base—used for primary actions, active navigation, tags, and data highlights so the product feels lively without overwhelming forms.
- **Documentary aesthetic:** Candid and intimate rather than heavily staged—real photography in empty states and headers where possible; comfortable typography (humanist sans, generous line height); subtle, natural motion; progressive disclosure for power features so everyday tasks stay simple.

**Implementation notes:**

- Drive appearance from **tenant theme tokens** (CSS variables or design tokens) loaded from configuration.
- Maintain **accessible contrast** for text and interactive elements (WCAG AA minimum); vibrant accents must not sacrifice readability.
- **Two density modes** optional later: “Floor” (larger targets) vs “Office” (more columns).

---

## 4. Multi-Tenancy & White-Label Branding

### 4.1 Tenant model

- **`tenant`:** The subscribing organization (customer of the SaaS).
- **`site`:** A physical property (hotel, lodge campus, standalone restaurant location).
- **`outlet`:** A logical venue within a site: `restaurant`, `bar`, `lounge`, `cafeteria`, `lodging_front_desk`, `retail`, `supermarket`, `event_space`, etc.

All transactional and master data that belongs to a customer is scoped by **`tenant_id`**, and usually by **`site_id`** / **`outlet_id`** where relevant.

### 4.2 Branding & configuration (per tenant)

- Business name, logo URL(s), favicon.
- **Theme:** primary, secondary, accent colors; optional border radius and font family from an allowlist.
- **Regional:** default currency, timezone, date format, first day of week.
- **Tax & legal:** default tax profiles, receipt footer text, registration numbers (display-only fields as needed).
- **Future:** custom domain, email sender branding, printable templates (PDF) using tenant tokens.

### 4.3 Isolation & security

- Enforce tenant isolation in the **database** (e.g. PostgreSQL **Row Level Security**) using `tenant_id` from the authenticated session—not only in application code.
- Separate **platform super-admin** from **tenant admin**; super-admin never appears in tenant UIs.

---

## 5. Feature Catalog

### 5.1 Identity, access, and administration

- Email (or SSO later) login; password reset; optional 2FA for managers and above.
- **Roles** (customizable labels, fixed capabilities): e.g. owner, tenant admin, site manager, outlet manager, front desk, server, bartender, kitchen, storekeeper, accountant read-only.
- **Outlet and site membership:** users see only assigned sites/outlets unless role is broad.
- **Invite users** by email: **`POST /api/v1/invites/`** (returns one-time token) and **`POST /api/v1/invites/accept/`** — **API implemented**. Staff deactivation and workspace PIN enrollment/revocation/idle-lock are implemented. Named workstation selection and device-linked shifts are now available; strong physical-device pairing and multi-till attribution remain tracked work.
- **Audit log:** who changed prices, performed refunds, adjusted stock, modified reservations (timestamp, user, entity).

### 5.2 Food & beverage (restaurant, bar, lounge, cafeteria)

- **Menu management:** categories, items, variants, modifiers, optional happy-hour or schedule-based price rules.
- **Outlet-specific menus:** same catalog can be enabled/disabled or price-overridden per outlet.
- **Service models:** dine-in with **tables**; quick retail bar; cafeteria tray/queue number (configurable).
- **Orders & tickets:** open tickets, add items, discounts (permissioned), service charge, tax lines, void/comp reasons (audited).
- **Settlement:** cash, card, split payments, tips (jurisdiction-dependent rules); payment provider integration as a pluggable layer.
- **Recipes / BOM (optional per item):** `GET/PUT …/menu/items/<id>/recipe/`; optional **`consume_recipe_on_sale`** so ingredient stock moves on **full pay** (after sale lines). **API implemented**; no modifier SKUs yet.
- **Kitchen display:** **`GET …/kds/tickets/`** (open orders, lines by station/status); **`POST …/orders/<id>/kds-line/`** to bump status. **API implemented**; no dedicated KDS web client in-repo.

### 5.3 Bar, parlor, and retail-style service

- Fast **SKU-first** selling; crate/bottle or custom unit support where applicable.
- **Stock assignments** to attendants (pattern from beer-parlor style flows) with reconciliation at shift end.
- **Reorder levels** and low-stock alerts per site or outlet.

### 5.3a Supermarket, retail shops, and convenience POS

The same **catalog + orders + payments** stack serves **grocery, supermarket aisles, convenience stores, pharmacies (non-regulated flows), and general retail**:

- **Sellable items** reuse **`menu_items`** as the product master: **SKU**, optional **barcode / PLU**, **unit of measure** (each, kg, lb, liter) for weighted or counted goods.
- **Outlet types** **`retail`** and **`supermarket`** signal UX defaults (e.g. scan-heavy till, optional tables hidden).
- **Per-outlet availability and price overrides** (existing outlet links) support different assortments or prices across branches.
- **Inventory (when enabled):** `track_inventory` on an item; **on-hand quantity per outlet**; **stock movements** (receive, adjust, waste); **automatic stock deduction when an order is paid** (same idempotent payment flow as hospitality POS).
- **Low-stock hints** via optional **`reorder_level`** per item and API filters for replenishment views.
- **Inter-outlet transfers**, **physical count sessions** (cycle counts), and **purchase orders** (suppliers, draft/send/receive) are implemented in the API.
- **Promotions** (time-bounded % or fixed discount, optional outlet scope): **`/api/v1/menu/promotions/`** + **`POST …/orders/<id>/apply-promotion/`** — **API implemented**.
- **Offline queue:** **`GET /api/v1/pos/catalog-version/`** (outlet-scoped menu fingerprint); **`POST /api/v1/pos/offline-sync/`** replays **`order_payment`**, **`order_create`**, and **`order_add_lines`** idempotently (`client_mutation_id`); optional **`catalog_version`** on menu-touching ops returns **409** when stale; **`POST /api/v1/pos/offline-sync/batch/`** drains up to 50 mutations with **per-index `results[]`** (HTTP 200 aggregate). Batch **`order_add_lines`** or **`order_payment`** may use **`depends_on`** (0-based index of a **prior** op) and omit **`order_id`** so the bill id is taken from that op’s **`applied_order_id`** (e.g. after **`order_create`** or **`order_add_lines`**) — **API implemented**; richer conflict UI remains roadmap.
- **Label printing** remains a roadmap item (hardware/bridge).

### 5.4 Hotel & lodge (rooms / units)

- **Room types** and **inventory** of units (rooms, cabins, sites).
- **Rate plans:** **`RoomRateWindow`** (date range + nightly amount per room type) via **`/api/v1/lodging/rate-windows/`** — **API implemented (yield-lite)**; automatic application to reservations / calendar UI not yet built.
- **Reservations:** create, modify, cancel with policy notes; optional deposit tracking.
- **Check-in / check-out**; **in-house** guest list.
- **Housekeeping status:** clean / dirty / inspected (configurable workflow).
- **Guest folio:** post F&B via POS when folio attached; **manual lines** on folio; **`POST …/lodging/reservations/<id>/post-folio-charge/`** for front-desk charges to an open folio on the same site. **Automatic room-night posting** not yet implemented.

### 5.5 Events & function spaces (optional module)

- **API implemented:** **`/api/v1/events/spaces/`**, **`/api/v1/events/bookings/`** (CRUD on bookings; deposits as fields). **Not yet:** calendar UI, conflict engine, packages, POS settlement link.

### 5.6 Inventory, purchasing, and suppliers

- **Stock ledger:** movements (purchase in, sale consumption, transfer between outlets/sites, adjustment, waste). **Implemented (MVP):** balances per outlet + manual movements + **sale** lines written on payment for tracked items.
- **Stock counts** with variance reporting.
- **Suppliers** master data; **purchase orders** (lightweight: draft → received) without full ERP complexity.
- **Perpetual inventory** for retail SKUs (`track_inventory`) and **recipes/BOM** (optional consumption on pay) are **implemented in the API** where noted above.

### 5.7 Reporting & exports

- Sales by outlet, channel, payment method, daypart.
- Product mix, top sellers, refunds and voids summary.
- Occupancy and simple revenue metrics for lodging (RevPAR-lite early).
- **Store/site-wise** comparisons for multi-site tenants.
- Export **CSV**; **PDF** summaries for managers; scheduled email reports (phase 2).

### 5.8 Platform & reliability

- **Health checks** and status for operators (pattern from existing health-check table concept).
- **Background jobs** for heavy exports and notifications.
- **Offline-tolerant POS:** partial — **`order_payment`** replay only (see §5.3a). Broader offline (new orders, conflicts) remains phase 2.

---

## 6. Data Model Sketch (high level)

Core entities (non-exhaustive):

- `tenants`, `tenant_settings`, `tenant_theme`
- `sites`, `outlets`, `outlet_types`
- `users`, `memberships` (user ↔ tenant/site/outlet + role)
- `menu_categories`, `menu_items` (incl. barcode, UoM, `track_inventory`, `reorder_level`), `modifiers`, `outlet_menu` (availability / price overrides)
- `orders`, `order_lines`, `payments`, `refunds`
- `stock_balances`, `stock_movements` (per outlet; sale on paid order)
- `tables`, `table_sessions` (where dine-in applies)
- `room_types`, `rooms`, `reservations`, `stays`, `folios`, `folio_lines`
- `inventory_items`, `stock_movements`, `stock_counts`, `suppliers`, `purchase_orders`
- `event_spaces`, `event_bookings` (API enabled)
- `room_rate_windows` (seasonal/yield-lite nightly rates per room type)
- `promotions`, `menu_item_recipe_lines` (BOM)
- `user_invites` (email invite flow)
- `offline_queued_operations` (client replay, `order_payment` only)
- `integration_links` (tenant integration registry)
- `audit_events`

Every row that carries customer data includes **`tenant_id`**. RLS policies restrict reads/writes to the tenant (and optionally outlet) of the session.

---

## 7. Technical Stack

**Current implementation:** **Django 5** + **Django REST Framework** + **Simple JWT** + **drf-spectacular** (OpenAPI 3, Swagger UI / ReDoc at **`/api/v1/schema/`**) in **`backend/`** (see [ARCHITECTURE.md](./ARCHITECTURE.md) §11 and [openapi.yaml](./openapi.yaml)). Default DB for local dev is SQLite; production should use **PostgreSQL** with **RLS** as described in the architecture doc.

**Staff UI in-repo:** **Django templates** (`apps/staff/`, Bootstrap CDN) with session auth; same JSON **API** remains for integrations, mobile, or third-party clients.

**Recommendation:** Keep **Postgres + RLS** for production tenant isolation; evolve the Django app as the system of record for auth, tenancy, and domain APIs.

---

## 8. Repository layout

| Path | Contents |
|------|-----------|
| `backend/` | Django project: tenants, sites, outlets, users, memberships, catalog (retail-ready SKUs, recipes, promotions), POS (incl. KDS + offline sync stub), **inventory**, lodging (incl. rate windows), **events**, **integrations** registry, audit, API v1 |
| `docs/` | This plan, [ARCHITECTURE.md](./ARCHITECTURE.md), [AUDIT_RECOMMENDATIONS.md](./AUDIT_RECOMMENDATIONS.md) (external audits → template-first actions), **[openapi.yaml](./openapi.yaml)** (exported schema) |

---

## 9. Additional Improvements (beyond initial description)

These strengthen the product for real-world SaaS without contradicting “simple for staff”:

1. **Onboarding wizard:** Create tenant → first site → first outlet → import menu CSV → invite first user.
2. **Sandbox / demo mode:** Sample data toggle for sales demos and training.
3. **Feature flags per tenant:** Enable lodging, events, or recipes only when subscribed.
4. **Billing integration:** Stripe (or similar) for subscription tiers, metered seats, or outlet packs.
5. **Localization:** UI strings + number/currency formatting; RTL later if needed.
6. **Print & hardware:** ESC/POS drivers or bridge app for receipts and kitchen printers (phase 2).
7. **Role templates:** “Bar staff”, “Hotel night auditor” one-click role bundles.
8. **Data retention & GDPR:** Export tenant data; delete tenant workflow; privacy policy hooks.
9. **Rate limiting & abuse prevention** on auth and public booking endpoints.
10. **Observability:** Structured logs, error tracking, per-tenant support impersonation (audited, owner-consented).

---

## 10. Phased roadmap (implementation status — API/backend)

| Phase | Scope | Status (Mar 2026) |
|-------|--------|---------------------|
| **MVP** | Tenants, branding tokens, sites/outlets, users/roles, menu + POS + payments, sales summary, Postgres RLS + optional GUC middleware | **Done** (payments support **partial pay** until balance zero; card = recorded method only, no PSP) |
| **v1.1** | Inventory, suppliers, POs, stock counts | **Done** (API) |
| **v1.2** | Lodging: room types, rooms, reservations, check-in/out, folios, manual lines, POS→folio on pay | **Done** (API); **+** reservation **`post-folio-charge`**; **no** auto room-night posting |
| **v1.3** | Recipes/BOM, KDS, offline POS queue | **Largely done (API):** recipe CRUD + optional consume on pay; KDS list + line status; offline **`order_payment`** replay only |
| **v2 (partial)** | Events, advanced rates, integrations hub | **Partial (API):** `events/spaces` + `events/bookings`; **`RoomRateWindow`**; **`integrations/links`** registry (no marketplace billing). **Not started:** mobile apps, full v2 UX |

**POS / settlement refinements shipped (API):** order-level **discount** (locked after any partial payment), **void line**, **add line**, **partial and final payments** with **`Idempotency-Key`**, **`amount_paid` / `balance_due` / `payments`** on reads, **refunds** against total paid with **`payment_id`** when split tender, optional **direct-sale restock** on final full refund, subtracting earlier line returns, **apply-promotion**.

**Gaps vs full product vision:** staff UI is **Django templates** (`/staff/`) — not a full **PWA/offline POS** yet; **password reset** via API + HTML confirm (no **2FA** yet); no **PSP webhooks**, no **CSV/PDF job** exports, no **label printing** or payment-provider **billing**; the modifiers model is now implemented — see §9.

---

## 11. Success Criteria

- A new tenant can **go live in under an hour** with **API + admin + `/staff/`** and one working outlet; **branded staff UI** uses tenant theme fields on server-rendered pages.
- A server can complete **sale → payment** via the **API** (or a client built on it); **minimal taps on a tablet** requires that client.
- **No cross-tenant data leakage** under penetration-style testing of the API and SQL layer.
- Managers can answer “**How did we do yesterday by outlet?**” without exporting to Excel (though export remains available).

---

## 12. Document Maintenance

- Update this file when scope, phases, or compliance requirements change.
- Link implementation specs (schema migrations, API OpenAPI, ADRs) from this doc as they are added to the repository.
- **Technical architecture and API outline:** [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Verticals vs shared backbone (bar, kitchen, PMS, retail, spa, events, mixed):** [MULTI_VERTICAL_OPERATIONS_REFERENCE.md](./MULTI_VERTICAL_OPERATIONS_REFERENCE.md)
- **External audits (recommendations mapped to Django templates):** [AUDIT_RECOMMENDATIONS.md](./AUDIT_RECOMMENDATIONS.md)
- **OpenAPI 3:** [openapi.yaml](./openapi.yaml) (export); live **`/api/v1/schema/swagger-ui/`** when `runserver` is up.

*Last updated: March 28, 2026*
