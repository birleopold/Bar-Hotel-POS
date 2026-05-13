# SYSTEMS directory audit

Reference folder: `SYSTEMS/` (bundled sample / reference apps). README and license files were skipped for code review.

## 1. `inventory-management-system-main` (Laravel + Blade + Vite)

**Stack:** Laravel, DTOs, service layer, MySQL-style migrations.

**Notable patterns**

- **Dashboard stats:** `DashboardStatsService` — aggregates revenue, COGS → gross profit, cash flow by category, **low stock** (`quantity <= min_stock`), top sellers, sales trend with **missing dates filled to zero**, top customers, expense breakdown. Uses **query-level aggregates** and short-lived **cache** keys.
- **Sales:** `SaleService` — transaction, `lockForUpdate` on products, stock decrement, line discounts capped by unit price, global discount capped by subtotal, cash tender validation.

**Shipped into HOTELNBARMGMT**

- **Low stock on staff Home:** `apps/staff/services/dashboard_insights.py` + dashboard template block, aligned with existing `StockBalance` / `MenuItem.reorder_level` and `staff-inventory-balances?low_stock=1` (same rule as API `low_stock` filter).

- **Sales snapshot on staff Home (second shipment):** same aggregates as **Sales summary** (`build_sales_summary`): default window **today − 7 days → today**, same outlet scope as the sales report (single outlet vs all outlets). **5‑minute cache** per tenant+scope+dates. Shows net sales, payment count, gross/refunds, top items by quantity, and **Full report** deep-links to `staff-sales` with matching `date_from` / `date_to`.

**Not ported (different product / phase)**

- Separate finance ledger (`FinanceTransaction` + categories) — your app uses POS payments/refunds and purchasing; a full cashbook would be a new module.
- Laravel-specific DTO/service layout — concepts already exist in Django services under `apps/pos`, `apps/inventory`.

---

## 2. `Asp.Net-Core-Inventory-Order-Management-System-ASP.NET-9.0`

**Stack:** Clean architecture, ASP.NET Core API, warehouses, delivery orders, stock counts, adjustments.

**Relevance**

- Rich **enterprise inventory** (multi-warehouse, transfers, sequences). Your app already has outlet-scoped stock, movements, counts, PO receive — overlapping domain, different schema.

**Shipped**

- No direct code copy (C# / different model). Ideas (sequence numbers, count statuses) are already represented in your migrations/services where needed.

---

## 3. `OdooHotelManagementSystem-10.0` (Odoo 10 modules)

**Stack:** Python 2-era Odoo ORM (not Django).

**Modules:** `hotel`, `hotel_reservation`, `hotel_housekeeping`, `hotel_restaurant`, POS bridge, reports.

**Relevance**

- **Housekeeping** activity types and room-linked tasks — maps to your roadmap (housekeeping vs room status). Porting would mean new Django models/views, not copying Odoo ORM.

**Shipped**

- No code import (incompatible framework). Terminology and flow remain guidance for future lodging features.

---

## 4. `php-inventory-management-system-master` / `InventoryManagementSystem-master` / `Mini-Inventory-and-Sales-Management-System-master` / `CustomerManagement-master` / `Restaurant-Management-System-master` / `SYSTEM-master`

**Observation**

- Older PHP / mixed layouts; CRUD-heavy, often without tests. **Restaurant-Management-System-master** had no `.php` hits in a quick glob (may be empty or non-PHP).

**Relevance**

- Useful as **UI/field checklists** only; your Django app is strictly ahead on multi-tenant POS, RLS, and API coverage.

**Shipped**

- No code copied.

---

## Summary

| Source | Action |
|--------|--------|
| Laravel IMS dashboard | **Implemented:** low-stock snapshot + cached **sales snapshot** (net, volume, top items) on staff Home; tests |
| Odoo hotel | Reference only for future housekeeping |
| ASP.NET / PHP demos | No merge; domain overlap with your existing inventory/POS |

Re-run tests: `pytest apps/staff/tests.py::StaffDashboardLowStockInsightTests apps/staff/tests.py::StaffDashboardSalesSnapshotTests`
