# P00 discovery checkpoint — 23 October 2026

Authority: [complete implementation roadmap](../../FIZO_COMPLETE_IMPLEMENTATION_ROADMAP_2026-10-23.md).
Source baseline: `8d45fb35bff514691b5650cdcc66f4e65c0902d5` on `main`.
Status: **in progress**, not phase completion. No new phase or product scope added.

## Fresh evidence

- [Baseline CI run](https://github.com/birleopold/Bar-Hotel-POS/actions/runs/40019088903): SQLite suite **83 failed, 801 passed, 7 skipped**, 1127 subtests passed. Django system and migration checks passed. PostgreSQL integration job passed; this is not restricted-role RLS or production certification.
- Existing route inventory now limits templates to Git-tracked files (avoids counting virtualenv templates) and emits literal template inheritance/include and CSS/JS links.
- Resolved inventory: **636 URL patterns**, including 281 generated admin, 188 API/data, 8 action/service and 159 visual candidates. **156 tracked templates**, with **28 visual candidates needing dynamic view/template tracing**.
- CSS dependency audit **fails** on eight links to missing files. Original results are preserved in `css-dependencies.json`. No files deleted or duplicate compatibility stylesheets created to conceal the failures.
- Local Django system check and migration-drift check passed after the inventory change. The full-suite count above is exact-baseline GitHub CI evidence, not a new local full-suite result for this documentation/inventory checkpoint.

| Broken asset | Consumers |
|---|---|
| `staff/hospitality-workflow.css` | KDS queue, orders list, shifts, table form |
| `staff/staff-theme.css` | Login, terminal, public signup |
| `staff/fizo-retail-sales.css` | Orders list |

The generated route business classification is a keyword-based discovery aid, **not an authorization or entitlement result**. Literal asset edges include conditional branches, not proof that every edge loads in every business. Dynamic templates, backend service/model writes, inherited cascade, middleware/permission enforcement and browser states require manual trace.

## Reproduction

Use the repository virtualenv and `DJANGO_SETTINGS_MODULE=config.settings.development`, `DATABASE_URL=sqlite:///:memory:`. From this directory run `../../../scripts/inventory_fizo_routes.py`; from repository root run `scripts/audit_css_dependencies.py` and capture its JSON. Both are read-only with respect to business data. CSS audit exit code 1 is an expected recorded failure at this baseline.

## Reference and acceptance boundaries

Four images supplied in this chat are already tracked in `docs/design/references/`: `industries.png`, `retail-dense.png`, `retail-comfortable.png`, `touch-pos.png`. The roadmap mentions five uploads; the fifth management image is not present in this chat's four attachments. Do not invent that baseline or claim its pixel acceptance.

No screenshots, browser comparison, production deployment, hardware, backup/restore or owner visual acceptance were collected in this discovery checkpoint. P00 stays open. Next work: trace the eight missing dependencies to canonical owners, categorize actual failing assertions from the exact CI run, and collect the five required viewport baselines before CSS replacement.

No migrations, financial writes, stock mutations, API changes or live service changes are included.
