# Platform Overview for Uganda

## Purpose
This platform is a Uganda-ready business operating system for businesses that run one or more branches and one or more sections under the same ownership.

It is designed for businesses such as:

- hotels and lodges
- bars and lounges
- restaurants and cafeterias
- supermarkets and retail shops
- spas and service businesses
- event and conference venues
- mixed businesses that combine several of the above

The goal is to let one business owner run all operations from one account, while each branch and section still works in a way that fits day-to-day reality on the ground.

**Industry context:** Bars, kitchens, hotels, cafeterias, retail, spas, and venues each have familiar “system names” (POS, KMS, PMS, RMS, and so on). What **cuts across** all of them on this platform is the same backbone: **orders and settlement**, **catalog**, optional **stock ledger** and counts, **section-based handoff**, **roles**, and **rolled-up reporting**, with **folios** where a guest stay ties charges together. A concise mapping of verticals to that backbone lives in **[MULTI_VERTICAL_OPERATIONS_REFERENCE.md](./MULTI_VERTICAL_OPERATIONS_REFERENCE.md)**.

Optional **EFRIS / fiscal** posture for Uganda is summarized in **[COMPLIANCE_EFRIS_POSTURE.md](./COMPLIANCE_EFRIS_POSTURE.md)** and does not replace legal or URA-specific advice.

## Product Positioning
This is not just a point-of-sale system.

It is a multi-branch, multi-section operations platform that helps a business manage:

- branches
- sections and outlets
- staff roles and access
- orders and operational handoff
- stock and purchasing
- rooms and guest folios
- services and service packages
- events and bookings
- reporting and oversight

For Uganda, the product should feel practical, familiar, and easy to run in a real business environment where one owner may operate:

- a hotel with a bar and restaurant
- a supermarket with a cafeteria
- a lodge with rooms, boat rides, massage, sauna, and conference space

## Operating Model
The platform should be understood in four layers.

### 1. Workspace
A workspace is the whole business account.

Examples:

- `Kampala Grand Hotel`
- `Mbarara Highway Stop`
- `Jinja Riverside Resort`

The workspace owns all branches, staff, stock records, services, and operating data.

### 2. Branch
A branch is a physical business location.

Examples:

- `Kampala Branch`
- `Entebbe Branch`
- `Jinja Site`

Each branch may contain several sections.

### 3. Section
A section is the operational unit where work happens.

Examples:

- bar
- kitchen
- restaurant floor
- front desk
- supermarket
- spa
- boat desk
- event space
- store

The section is what determines workflow, visibility, and responsibility.

### 4. Workstation / Till
A workstation or till is where staff actually do work.

Examples:

- front-desk terminal
- bar till
- supermarket cashier lane
- kitchen screen
- spa booking desk

## Core Design Principles

### One business account, many sections
One business should not need different systems for rooms, drinks, food, services, and stock.

### One order where appropriate
Food, drinks, and services can live on one order when that matches the operation, but each line must still route to the correct section.

### Section ownership
Each section should only see and act on what belongs to it operationally.

Examples:

- kitchen sees kitchen lines
- bar sees bar lines
- spa desk sees service lines
- front desk sees reservations, folios, and room operations

### Shared reporting backbone
Management should see a unified picture of performance, while revenue and operations still roll up by section, branch, and workspace.

### Practical Uganda-first terminology
The UI should use labels that make sense locally:

- branch
- section
- till
- room charge
- stock receive
- stock take
- goods received
- shift close
- ready for serving

### Template-first operations
The product should remain fast and easy to operate in server-rendered screens, with focused UI polish where operational speed matters.

## Current Platform Scope
The current system is already moving toward this operating model.

### Staff operations

- dashboard
- orders
- tables
- prep queue
- menu view
- sales summary
- stock balances and stock ledger
- stock receive, transfer, and stock counts
- purchasing and supplier flows
- reservations, folios, rooms, and room types
- events and spaces
- workspace settings and team management

### Console administration

- organization overview
- guided setup
- branches/properties and outlets
- menu categories and items
- services and service packages
- room types, rooms, and rate setup
- platform-level workspace and plan management

## Uganda-Fit Business Flows

Flows below are grouped by **business intention**—what the owner and staff are trying to achieve that day—not by software module names. Several intentions can run at the same branch (for example hotel + bar + retail).

### Intention: Fast bar and lounge service

**Goal:** Quick rounds, tabs, and tight control of drink stock and consistency.

1. Bartender or server opens an order (often table- or tab-oriented).
2. Drink lines route to the **bar** section; each sale can drive **recipe/BOM** consumption where configured.
3. Payments, split bills, and shift close follow the same order backbone as other outlets.
4. Management reviews sales and stock movement by bar section; physical counts explain variance.

### Intention: Coordinated restaurant and kitchen

**Goal:** Food prepared on time, visible to the right station, without the bar or front desk noise.

1. Server opens order; **food** lines route to **kitchen** (and drinks to bar when both exist).
2. Kitchen uses **prep queue / KDS-style** views to bump status and hand off when ready.
3. Front-of-house sees readiness for serving; management sees kitchen vs floor performance separately.

### Intention: Cafeteria or high-volume queue

**Goal:** Move lines quickly; often batch-oriented production rather than per-table pacing.

1. Staff opens order at till (or configured quick-sale pattern); optional ticket/queue identity instead of full table service.
2. Items that need production route to kitchen or bar sections as usual.
3. Stock and promotions behave like other outlets; heavy enterprise patterns (payroll deduction, corporate meal IDs) are integration-phase concerns—the core remains **sell → fulfill → pay → ledger**.

### Intention: Hotel or lodge guest stay

**Goal:** One guest, one stay, one place for room and extras to accumulate until checkout.

1. Reservation and **check-in** create or attach the **guest folio** and room state.
2. **Housekeeping** status updates feed front desk readiness for the next guest.
3. Bar, restaurant, spa, or retail charges can **post to folio** when the guest is in-house and the workflow allows it.
4. Front desk **settles** the folio; room revenue and F&B/services roll up in reporting.

### Intention: Supermarket or retail checkout

**Goal:** Accurate, fast SKU selling and trustworthy stock for replenishment.

1. Cashier opens order; items added by **scan** or quick lookup (SKU/barcode where used).
2. On payment, tracked items reduce **on-hand** per outlet rules.
3. **Receiving, transfers, counts, and purchase orders** support restocking without duplicating a separate retail database.

### Intention: Spa, activities, and service sales

**Goal:** Sell time- or package-based services and route work to the right desk or section.

1. Admin defines **services** and **packages** once.
2. Staff adds service lines to orders; lines route to the appropriate **service** section (spa, boat desk, etc.).
3. Consumables can sit on **section-scoped stock** where the business tracks oils, towels, or parts.
4. For lodging, services may post to **folio** like F&B when that fits the operation.

### Intention: Events, conference, and function space

**Goal:** Reserve space, capture deposits and expectations, align catering and operations for a specific date.

1. **Spaces** and **bookings** record the event skeleton (timing, deposit fields, notes).
2. Catering and F&B execution still flow through normal **orders** and sections as the business operates day-of.
3. Owner reporting combines **event** revenue signals with **outlet** performance as modules mature.

### Intention: Mixed business under one owner

**Goal:** One dashboard, no duplicate silos—hotel plus bar plus shop plus spa, etc.

1. **Workspace** stays one; **branches** and **sections** model each concept.
2. **Cross-charging** (e.g. shop or spa to room) uses **folio** and guest context where enabled.
3. **Unified reporting** rolls up by section and branch while keeping operational screens section-focused.

**Deeper vertical comparison table and industry terminology:** see **[MULTI_VERTICAL_OPERATIONS_REFERENCE.md](./MULTI_VERTICAL_OPERATIONS_REFERENCE.md)**.

## Roles
The system should keep role naming simple and business-friendly.

### Platform roles

- Platform Owner
- Platform Staff

### Workspace roles

- Owner
- Tenant Admin
- Site Manager
- Outlet Manager
- Server
- Bartender
- Kitchen
- Front Desk
- Storekeeper
- Accountant

This role model should continue to be enforced through scoped visibility and action permissions.

## Stock and Section Responsibility
Stock should be managed in a way that reflects how mixed businesses really operate.

Examples:

- kitchen stock for ingredients
- bar stock for beverages
- store stock for supermarket items
- spa or service consumables for oils, scrubs, towels, and supplies

The system should support:

- single item stock receive
- bulk CSV stock receive
- stock transfer
- stock take
- purchase order receiving

Operational ownership can vary by business, but the platform should support:

- storekeeper-led receiving
- manager-led adjustment
- section-level stock visibility

## Reporting View
The reporting model should be unified but section-aware.

Examples of useful rollups:

- workspace-level summary
- branch-level summary
- section-level summary
- stock movement by outlet
- service performance by package
- food versus drinks versus services

The principle is simple:

- one management view
- many operational views

## What This Platform Is Becoming
The platform should be positioned as:

> A Uganda-ready multi-branch operations platform for hospitality, retail, and service businesses. It gives each business one workspace, one operating backbone, and one reporting picture, while still letting each branch and section work in a way that matches how business is actually run on the ground.

## Near-term implementation sequence (before integrated payments)

**Decision:** Build out **operational depth and platform reliability first**; tackle **unified payments** (card rails, mobile money orchestration, fiscal compliance) **only after** the themes below are in strong shape. Recorded tenders (cash/card/other as methods) remain the working model until then.

Aligned with the technical roadmap in [HOSPITALITY_SAAS_PRODUCT_PLAN.md](./HOSPITALITY_SAAS_PRODUCT_PLAN.md) and [AUDIT_RECOMMENDATIONS.md](./AUDIT_RECOMMENDATIONS.md).

| Order | Theme | What “done enough” means |
|------|--------|---------------------------|
| **2** | **Offline POS v2** | Move beyond idempotent **payment replay**: resilient local cart, menu/catalog version pins, sync queue, and clear handling when server and device disagree. |
| **3** | **Menu intelligence** | First-class **modifiers** (option groups), bundles where needed, dietary/allergen signals, and sensible **print/KDS routing** rules per item or category. |
| **4** | **Lodging depth** | **Nightly room charges** resolved from rate windows (and overrides), staff-facing **calendar / tape-chart** basics, and **housekeeping** workflows tied to room status—not only API CRUD. |
| **5** | **Events depth** | **Calendar** and **conflict** visibility, packages/deposits as operational objects, and **settlement links** to orders or folios where the business sells events like other revenue. |
| **6** | **Reporting layer** | Outlet- and section-aware **rollups**, **CSV** exports on key staff reports (sales summary, cashbook), optional **scheduled** summaries—without blocking day-to-day POS. |
| **7** | **Jobs & observability** | **Background workers** for heavy exports, notifications, and integration fan-out; **structured logs** with tenant/outlet/**site** context on sensitive actions (`JSON_LOGS`). |
| **8** | **Staff / API parity** | A maintained **matrix** (feature × staff UI × API × tests) so integrators and floor staff do not drift; same business rules in one place. **Living doc:** [STAFF_API_PARITY.md](./STAFF_API_PARITY.md). |

**Optional EFRIS (Uganda fiscal):** an **opt-in** HTTP adapter and outbox queue ship **in parallel** with the themes above so tenants can enable compliance without blocking core ops. Posture and limitations: [COMPLIANCE_EFRIS_POSTURE.md](./COMPLIANCE_EFRIS_POSTURE.md).

**Later (after 2–8):** integrated **PSP / MoMo**, **webhooks**, reconciliation, and **certified/production EFD** alignment where required—documented in a dedicated payments spec.

## Deferred Areas
The following stay **lightly scoped** in this overview; deep specs live in linked documents:

- **Payment rails:** detailed card / mobile money architecture, webhooks, and reconciliation (see product plan when that phase starts).
- **Tax and fiscal certification:** URA integration **behaviour** is described in [COMPLIANCE_EFRIS_POSTURE.md](./COMPLIANCE_EFRIS_POSTURE.md). Production go-live still requires environment-specific validation with URA or an approved EFD vendor.

This overview remains the **product intent** document; technical deployment checklists should stay next to the code they describe.
