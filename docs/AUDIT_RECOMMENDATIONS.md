# External audits — consolidated recommendations (Django templates only)

This document captures two independent codebase audits of **HOTELNBARMGMT** (platform-level + file-by-file / premium-SaaS roadmap) and **filters them for how this product is actually built**: a **Django monolith** with **DRF** for `/api/v1/` and **server-rendered staff UX** under `/staff/` (and related template-driven surfaces).  

**Non-goal for this doc:** recommending a separate SPA (React/Next/Vue) as the primary staff or POS UI. Richer behavior should stay compatible with **Django templates**, **shared CSS/tokens**, and **small, targeted JavaScript** where needed (e.g. existing WebSocket refresh on kitchen queue). If a future client needs a native or SPA shell, the API can serve it; that is not the default delivery model documented here.

For system shape and API outline, see [ARCHITECTURE.md](./ARCHITECTURE.md). For product vision and personas, see [HOSPITALITY_SAAS_PRODUCT_PLAN.md](./HOSPITALITY_SAAS_PRODUCT_PLAN.md).

---

## 1. What both audits agree you already do well

- **Domain decomposition** — apps aligned to hospitality areas (`tenants`, `pos`, `inventory`, `lodging`, `staff`, `api`, etc.).
- **Multi-tenancy** — `Tenant` / `Site` / `Outlet`, membership, middleware-scoped tenant context, optional Postgres RLS path.
- **Serious POS and ops concepts** — orders, payments/refunds with idempotency, offline queue, folios, stock movements, audit trail intent.
- **Two delivery modes** — JWT API + session-based staff UI; pragmatic for internal tools and integrators.
- **UUIDs, constraints, money as `Decimal`** — sensible for integrations and distributed-friendly APIs.

These are worth **preserving** while hardening everything around them.

---

## 2. Relevant themes — interpreted for this stack

### 2.1 Presentation layer (staff UX)

**Audit concern:** Template-heavy UIs struggle with very rich, real-time, tablet-first workflows compared to a full SPA.

**Relevant response (templates only):**

- Treat **staff templates** as a **product surface**: role-aware nav, persistent tenant/site/outlet context in the chrome, **action-first** dashboard entry points (same ideas as the product plan §1–2).
- **Tablet-first** layouts and touch targets via CSS (existing staff theme direction); avoid coupling “premium UX” to a framework change.
- **Live KDS / live ops:** prefer **Django Channels** + small in-template scripts (pattern already usable for kitchen refresh) rather than a new frontend stack.
- **Large form files** (`apps/staff/forms.py`): split by **domain** (orders, inventory, lodging, …) and reuse **service-layer** validation so templates and API do not diverge.

### 2.2 Observability and operations

**Audit concern:** Thin logging and weak production signal.

**Relevant response:**

- **Structured logging** and **request correlation** — implemented in backend via configurable JSON logging, request ID middleware, and optional Sentry (`SENTRY_DSN`, `JSON_LOGS`, `LOG_LEVEL` in env). Extend **log context** over time (tenant id, outlet id, user id on sensitive actions) in services, not only in views.
- **Standard API error shape** — evolve DRF toward a **consistent JSON contract** (code, message, `request_id` where applicable) without changing template strategy.

### 2.3 Security and platform hygiene

**Audit concern:** Default `SECRET_KEY`, minimal `production.py`, rate limits on sensitive endpoints.

**Relevant response:**

- **`config/settings/production.py`** should be expanded (not replaced) with **secure cookies**, **HSTS**, **SSL redirect**, **trusted proxy / `SECURE_PROXY_SSL_HEADER`**, and **fail-closed** checks for `SECRET_KEY` and critical env in production.
- **Rate limiting** — throttled JWT and high-abuse routes (e.g. offline sync) align with audit; extend to **password reset**, **invite accept**, and other public-ish endpoints as needed.
- **CORS / allowed hosts** — keep environment-specific lists explicit for staging vs production.

### 2.4 Performance and scalability

**Audit concern:** No caching, hot tables, reporting vs OLTP.

**Relevant response:**

- **Redis** optional for cache, channel layer, and future workers (`REDIS_URL`); **menu list caching** (ordered PK cache per tenant/outlet) reduces catalog read load for POS-style list endpoints.
- **Query hygiene** — `select_related` / `prefetch_related` on orders, lines, KDS ticket payloads; review as serializers grow.
- **Reporting** — keep transactional models clean; plan **read models / summaries** later (materialized views or ETL) without blocking current template features.

### 2.5 Async and resilience

**Audit concern:** Everything synchronous; emails and heavy work in-request.

**Relevant response:**

- Introduce **Celery (or RQ / Django-Q) + Redis** when email volume, reports, or webhooks justify it — **orthogonal** to templates.
- **Domain events** (even as simple internal signals + later queue tasks) for “order paid”, “low stock”, etc., stay backend concepts.

### 2.6 SaaS control plane and entitlements

**Audit concern:** Thin billing, plans, tenant lifecycle, feature entitlements.

**Relevant response:**

- Add **explicit models** (plan, subscription state, module entitlements) and surface them in **console** and **staff** where appropriate — still Django views and templates.
- **`enabled_staff_modules` JSON** is a stopgap; long-term **entitlement resolution** should live in a small service layer callable from API and staff.

### 2.7 Audit and compliance story

**Audit concern:** Generic audit rows; thin `audit/services.py`.

**Relevant response:**

- Enrich **audit payload** with **request id**, **source** (staff vs API), and **before/after** for sensitive fields where feasible.
- Keep **technical logs** (structured) separate from **business audit** (DB events) but **correlatable** via request id.

---

## 3. File-level hotspots (from file-by-file audit) — still relevant

| Area | Files | Template-native direction |
|------|--------|---------------------------|
| Production safety | `config/settings/production.py`, `base.py` | Expand secure defaults; validate env in production. |
| API surface growth | `apps/api/urls.py` | Optional future split by **tag** or **sub-include**; versioning discipline on `/api/v1/`. |
| Tenant middleware | `apps/api/middleware.py` | Unified error JSON + logging on resolution failures. |
| Permissions | `apps/api/permissions.py` | Introduce composable policies as complexity grows. |
| Invites / reset | `apps/api/invite_views.py`, `password_views.py` | Lifecycle states, async email, throttles, safer edge cases for existing users. |
| Accounts / tenants | `apps/accounts/models.py`, `apps/tenants/models.py` | Lifecycle and entitlement models when you sell SaaS tiers. |
| POS core | `apps/pos/models.py`, `apps/pos/services.py`, `apps/pos/views.py` | Split **services package**; keep viewsets thin; shifts/registers only when product requires. |
| Inventory / lodging | `apps/inventory/*`, `apps/lodging/models.py` | Deeper operational models over time; events for alerts. |
| Staff UI | `apps/staff/views.py`, `urls.py`, `services.py`, `forms.py`, templates | Smaller modules; workflow-oriented dashboards; template partials for reuse. |
| Console | `apps/console/mixins.py` | Stronger admin audit and permission granularity. |
| Audit | `apps/audit/models.py`, `services.py` | Richer schema + builder pattern. |

---

## 4. Phased roadmap (premium SaaS — **without** changing frontend technology)

Aligned with audit “phases” but **scoped to Django + templates**:

| Phase | Focus |
|-------|--------|
| **0** | Product pillars unchanged (see product plan). |
| **1** | Production settings, Postgres in real deploys, structured logs + Sentry + request ID, throttles, tests on tenant boundary + payments + stock + invites. |
| **2** | Modular monolith: split `pos/services`, `staff/forms`, `staff/services`; commands vs queries inside Python packages. |
| **3** | Staff **experience** in templates: role dashboards, action shortcuts, clearer context chrome; live kitchen via Channels + minimal JS. |
| **4** | Guided **workflows** (onboarding, first outlet, stock receive) as dedicated template flows. |
| **5** | **Control plane**: billing/plan/lifecycle models + console/staff configuration UIs. |
| **6** | Workers + real-time expansion (email, reports, webhooks, stock alerts). |
| **7–8** | Reporting read models, enterprise audit, integrations. |

---

## 5. Already reflected in the current backend (audit alignment)

The following were added or configured to match earlier audit priorities while **keeping** staff as Django templates:

- Request ID middleware and optional **JSON log lines**; optional **Sentry** when `SENTRY_DSN` is set.
- **Django Channels** ASGI routing, Redis or in-memory channel layer, **KDS WebSocket** group updates on line changes, staff kitchen template refresh hook.
- Optional **Redis** cache (`django-redis`) with LocMem fallback; **menu PK list cache** for outlet-scoped catalog list with invalidation on catalog changes.
- **DRF scoped throttles** on JWT obtain/refresh, POS offline sync, and **invite accept** (`invite_accept` scope).
- **Prefetch / select_related** improvements on orders and KDS queries where listed.
- **pytest** + sample API health test under `backend/tests/`.
- **`config/settings/production.py`**: fail-closed **`SECRET_KEY`** (rejects dev default), **secure cookies**, **HSTS**, **SSL redirect**, optional **`SECURE_PROXY_SSL_HEADER`** via `USE_X_FORWARDED_PROTO`, **`CSRF_TRUSTED_ORIGINS`** from env.
- **Unified API error JSON** via `REST_FRAMEWORK["EXCEPTION_HANDLER"]` (`apps.api.exceptions.api_exception_handler`): responses include `error` (`code`, `message`, `details`) and **`request_id`** when known; tenant middleware JSON errors include `request_id` and log `tenant_forbidden` / invalid header.
- **Invite accept** throttling and fix for **`timezone`** usage in `invite_views.py`.

**Modular monolith (Phase 2, implemented):** `apps/pos/services/` now has explicit `commands.py` (write paths) and `queries.py` (read/pure paths), while preserving the stable `apps.pos.services` public API through re-exports. `apps/staff/services/` similarly exposes `queries.py` plus `commands.py` as the write-path home for future staff mutations, with compatibility preserved via `apps.staff.services` exports. `apps/staff/forms/` remains split by domain (auth, lodging, inventory, events, purchasing, POS orders, promotions, workspace/branding), with imports from `apps.staff.forms` unchanged.

**Phase 3–5 (implemented core) + Phase 6+ (in progress):** Staff **action-first dashboard** — `staff_dashboard_actions()` builds role-ordered primary/secondary tiles on `/staff/` (`dashboard_actions.py` + template “Start here”). **Context chrome** is present across staff pages (workspace/property/outlet pills). **Live kitchen** runs via Channels WebSocket (`/ws/kds/...`) with minimal template JS plus reconnect/backoff/status-pill handling and fallback refresh. **Guided setup workflows** are active in Console + Staff with shared `phase4_control_panel` partial, persistent setup progress, first stock receive step, and manual per-step states (`skipped` / `blocked` / reset). **Control plane core** now includes platform plans, tenant subscription lifecycle states (`trial` / `active` / `past_due` / `suspended` / `cancelled`), tenant feature entitlement overrides, server-side staff module resolution enforcing plan + entitlement gating, and template-first billing operations (invoice placeholders + billing event timeline + explicit transition workflow, including `past_due -> suspended`). **Supermarket/retail POS groundwork** now includes SKU profile metadata (barcode/PLU/weighted flags), barcode/PLU add-to-cart commands, line-level discount handling, supermarket order-detail template routing for `supermarket`/`retail` outlets, line return + restock flow, and POS shift open/close placeholders with audit logs. **Audit payloads** — `AuditRequestContextMiddleware` + `log_audit(..., request_id=, source=)` merge `request_id` and `source` (`api` / `staff`) into each event’s JSON `payload` for API and staff routes. **Celery** — `config/celery.py`, `apps/api/tasks.py` (`send_password_reset_email_task`); `CELERY_BROKER_URL` defaults to `REDIS_URL` or `memory://`; `CELERY_TASK_ALWAYS_EAGER` is **True** in `development.py` (no worker); with Redis in production set `CELERY_TASK_ALWAYS_EAGER=False` and run `celery -A config worker -l info`. **POS API** — `apps/pos/view_helpers.py` centralizes idempotency header, line/menu/promotion resolution for `OrderViewSet`.

Treat this list as **foundation**, not “done”: more async tasks (reports, webhooks), staff workflow wizards, and DB-level audit indexing remain optional follow-ups.

---

## 6. Explicitly out of scope for this documentation set

- Adopting **Next.js / React / Vue** (or similar) as the **primary** staff or POS UI.
- Replacing DRF with another API style (unless a future doc proposes it).

Third-party **mobile or POS clients** may still consume **the same JSON API**; that does not change the **canonical** staff experience described here.

---

## 7. How to use this doc

- **Engineering:** Prioritize `production.py` + `base.py` safety, then service boundaries, then template/dashboard workflow work.
- **Product:** Use §2.1 and phase **3–4** for roadmap conversations without assuming a SPA.
- **Audits:** This file is the **single internal index** of external review outcomes adapted to repo conventions; update it when major recommendations are implemented or deferred.
