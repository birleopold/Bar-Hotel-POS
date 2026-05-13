# Multi-vertical operations reference

This document explains how **specialized industry systems** (bar POS, kitchen display workflows, property management, retail, spa, venues) relate to each other—and how they map onto **one workspace** in this platform. It complements [PLATFORM_OVERVIEW_UGANDA.md](./PLATFORM_OVERVIEW_UGANDA.md), which is the primary place for **Uganda-fit flows** and operating vocabulary.

For API and implementation status, see [HOSPITALITY_SAAS_PRODUCT_PLAN.md](./HOSPITALITY_SAAS_PRODUCT_PLAN.md) and [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## What cuts across every vertical

Regardless of whether the business is a bar, hotel kitchen, cafeteria lane, supermarket till, spa desk, or event hall, the same **operational backbone** shows up again and again. On this platform that backbone is intentionally shared:

| Capability | What it means in practice |
|------------|---------------------------|
| **Selling & settlement** | Orders, line items, discounts, voids (audited), payments, split or partial pay, tips where applicable. |
| **Catalog** | Items (including SKU/barcode for retail), categories, modifiers, outlet-specific availability and prices. |
| **Stock truth** | Optional per-item tracking, movements on receive/transfer/adjust/waste, consumption on sale or recipe rules, physical counts and variance. |
| **Operational handoff** | Lines or tickets visible to the right **section** (bar, kitchen, store, front desk, spa) without exposing the whole order everywhere. |
| **Roles & access** | Who can sell, receive stock, change prices, close shifts, or see management reports—scoped by branch and section where needed. |
| **Reporting** | Rollups by workspace, branch, and section so owners see one picture while teams see only their workload. |
| **Guest or account context (when relevant)** | In lodging, a **folio** ties room, F&B, and services into one running bill; retail-only sites may never use folios. |

**Design implication:** Vertical-specific tools (KDS, housekeeping boards, event calendars) are **views and rules** on top of this backbone—not separate products that duplicate orders and stock.

---

## Bar and lounge systems

**Industry framing:** A bar-focused stack emphasizes **speed**, **open tabs**, **consistent pours**, and tying **every sale to inventory** (bottles, shots, mixers) so shrinkage and pour cost are visible.

**Typical loop:** take order → ring items → optional recipe/BOM consumption → payment or tab → shift reporting (sales, tips, inventory variance cues).

**On this platform:** Use a **bar** (or lounge) **section** and tills; route drink lines to bar; enable **recipes / BOM** where depletion should track ingredients; use stock receive, counts, and reorder hints for par-level discipline. Complex hardware (integrated scales, dedicated pour spouts) is out of scope for the core product description but does not change the data model: counts and sales still reconcile to the same ledger.

---

## Restaurant and kitchen coordination (KMS-style)

**Industry framing:** Kitchen management is less about tabs and more about **synchronizing stations**—grill, salad, fry—and **timing** so courses for one table finish together. Digital **kitchen display** replaces or augments paper chits; an **expediter** view shows what is ready vs in progress.

**On this platform:** Food lines route to a **kitchen** section; **prep queue** and **KDS-oriented APIs** support bumping line status and station visibility. Full “automatic fire times” per course are a maturity feature; the important fit is **one order, multiple destinations**, with kitchen seeing only its lines.

---

## Cafeteria and high-throughput food service

**Industry framing:** Cafeterias optimize **queues** and **batch production**: kiosks or QR ordering, pre-orders from desks, **pickup windows**, and alerts when a batch (e.g. daily special) is running low. Payment may be **cashless** or tied to payroll or meal credits in large organizations.

**On this platform:** The same order and catalog stack supports **fast counter-style** selling; **tables** may be optional or replaced by queue/ticket semantics depending on outlet configuration. Enterprise-specific integrations (payroll deduction, corporate IDs) belong in a later integration phase; the operational core remains **order → kitchen/bar as needed → pay → stock**.

---

## Hotel and lodge (property management)

**Industry framing:** A **PMS** owns the **guest journey**: search and booking, room inventory, check-in/out, **master folio** for all charges, housekeeping status, and often **channel** connectivity so OTAs and the website do not overbook. **RMS** (revenue management) adjusts rates by demand—often a separate or advanced module.

**On this platform:** **Reservations**, **stays**, **folios**, **room** and **rate** setup, and **housekeeping** status align with PMS responsibilities; **POS** posts F&B and services to an in-house folio when the guest context is attached. Deep channel-manager or RMS automation is not required to describe the core loop: **guest in house → charges accumulate → settle at front desk**.

**Clarification:** **PMS** optimizes **room nights and guest records**; **POS** optimizes **line-item sales and tender**. They integrate at the folio and guest-identification boundary.

---

## Supermarkets and retail shops

**Industry framing:** Retail systems emphasize **large SKU counts**, **barcode scanning**, **fast checkout**, and sometimes **expiry** and **markdown** discipline. **Vendor-managed** replenishment and **loss prevention** (void patterns, self-checkout anomalies) are common add-ons.

**On this platform:** **Menu items** double as product master with **SKU**, optional **barcode**, **unit of measure**, and **`track_inventory`**; stock moves on paid sales; **promotions**, **transfers**, **counts**, and **purchase orders** support replenishment. Advanced grocer-only features (automated expiry workflows, supplier portal VMI, LP ML) are not assumed in the base docs but sit naturally as extensions of the same **catalog + ledger + audit** model.

---

## Spas and service businesses

**Industry framing:** Spa systems stress **appointment density**, **room and equipment allocation** (avoid double-booking a room or machine), **packages and memberships**, and often **intake or consent** forms before treatment.

**On this platform:** **Services** and **service packages** attach to orders like other sellable lines; routing can go to a **spa** (or named service) **section**. A full **calendar and resource scheduler** for every chair and room is a phased capability—see non-goals in [PRODUCT_REQUIREMENTS_UGANDA.md](./PRODUCT_REQUIREMENTS_UGANDA.md)—but **selling**, **posting to folios**, and **consumable stock** for treatments still use the shared backbone.

---

## Event and conference venues

**Industry framing:** Venue software tracks **inquiries → contracts → deposits**, **function sheets (BEOs)** so catering, AV, and security share one timed plan, and sometimes **seating layouts**. It behaves partly like a CRM for the event sale and partly like operations for the day-of run sheet.

**On this platform:** **Event spaces** and **bookings** exist in the API; linking deposits, catering packages, and day-of execution UI evolves over time. **Mixed venues** still benefit today from **one workspace**: room blocks, F&B orders, and event charges can be reasoned about under shared reporting even before every BEO automation ships.

---

## Mixed and multi-concept businesses

**Industry framing:** Hotels with retail, spa, and conference space need **unified guest or customer context**, **cross-department charging** (e.g. retail or spa to room), and **one owner dashboard** instead of siloed apps.

**On this platform:** **Branches** and **sections** model multiple concepts under one **workspace**; **folio posting** connects lodging to POS and services; reporting stays **section-aware** while rolling up for the owner. The goal is to avoid maintaining separate stock and order histories per silo.

---

## At-a-glance: primary goal by vertical

| Vertical | Primary operational goal | Distinctive emphasis (beyond the shared backbone) |
|----------|-------------------------|---------------------------------------------------|
| Bar / lounge | Fast rounds, tabs, pour consistency | Recipe/BOM, bar stock, shift variance story |
| Restaurant / kitchen | Timed, accurate food production | Station routing, KDS/prep status |
| Cafeteria | Throughput and batch alignment | Queue/kiosk patterns, batch signals (conceptual + config) |
| Hotel / lodge | Guest stay and room inventory | Folio, housekeeping, reservations |
| Retail / supermarket | Accurate SKU checkout and replenishment | Barcode, scale UoM, high SKU count |
| Spa / services | Resource and package scheduling | Appointments, rooms/equipment (maturity varies) |
| Events / conference | Contract and run-of-show coordination | Spaces, bookings, BEO-style detail (maturity varies) |
| Mixed | One business, many revenue lines | Cross-charge, unified reporting, section boundaries |

---

## Where to read next

- **Flows and Uganda terminology:** [PLATFORM_OVERVIEW_UGANDA.md](./PLATFORM_OVERVIEW_UGANDA.md) — *Uganda-Fit Business Flows* and *Operating Model*.
- **Requirements and non-goals:** [PRODUCT_REQUIREMENTS_UGANDA.md](./PRODUCT_REQUIREMENTS_UGANDA.md).
- **Roadmap and API reality:** [HOSPITALITY_SAAS_PRODUCT_PLAN.md](./HOSPITALITY_SAAS_PRODUCT_PLAN.md).

*This reference is product vocabulary and mapping; it is not a vendor comparison or implementation checklist for third-party PMS/POS products.*
