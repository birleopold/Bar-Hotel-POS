# Contributing

## Development workflow

1. Create a focused branch from `main`.
2. Keep domain rules in services or models rather than duplicating them across staff and API views.
3. Apply tenant, site, outlet, and role scope before reading or writing business data.
4. Add migrations for schema changes.
5. Add meaningful tests for permissions, transitions, financial effects, or tenant isolation.
6. Run the checks below before opening a pull request.

```powershell
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp
```

## UI conventions

- Use the shared staff and console shells.
- Keep desktop navigation in the left rail and preserve compact mobile navigation.
- Reuse staff cards, buttons, fields, tables, alerts, and status treatments.
- Make outlet and site context visible where it affects data.
- Use the terminology in [`docs/UI_TERMINOLOGY_GUIDE.md`](docs/UI_TERMINOLOGY_GUIDE.md).

## Workflow rules

- Use authoritative services for reservation, folio, payment, refund, purchasing, and stock transitions.
- Keep financial and inventory history append-oriented and auditable.
- Protect commands against duplicate submission where financial or stock effects are possible.
- Treat source tests, deployment, provider acceptance, and physical device validation as separate proof boundaries.

## Commit messages

Use concise, action-oriented messages, for example:

```text
feat: add partial purchase receipt history
fix: enforce tenant scope for sales reports
docs: add production operations runbook
```
