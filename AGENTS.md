# Codex operating instructions — Bar-Hotel-POS

Read **this file** and `docs/CODEX_HANDOFF_2026-10-16.md` before making changes. The authoritative 34-item product checklist is `docs/SUITE_IMPLEMENTATION_TODO.md`. Resume from actual source code and fresh CI evidence, never from an assistant's unsupported claim of completion.

## Owner's non-interactive implementation rules

1. Work autonomously; do not ask the owner questions or request approval between implementation steps. The owner wants an implementation-first pass, with verification as a separate activity where requested. Still report tests honestly and never bypass checks or pretend that unexecuted tests passed.
2. Research and cross-check current documentation, relevant professional projects and established implementations online before significant design decisions. Focus on **Uganda**; do not add Kenya, Rwanda or Tanzania country adapters.
3. Use plain, user-friendly terminology; make every workflow simple and professional.
4. No duplicate implementations. Locate and extend existing domain services, views, API endpoints, Django forms, migrations, templates and shared navigation before creating new code.
5. Treat a feature as implemented only when the actual end-user can reach and use it, with complete backend, authorization, business/tenant/outlet scoping, validation, UI, API where applicable, migrations, audit and tests.
6. Design and verify for desktop, laptop, tablet, mobile and large displays, including touch, keyboard, assistive technology and meaningful empty/error states.
7. Preserve existing working behavior; avoid unnecessary new frameworks, microservices, React rewrite, Docker/Kubernetes requirements or parallel financial ledgers.
8. Complete substantial related workflows and phases, not isolated cosmetic commits. The owner specifically targets **9 of 34 phases implemented and locally verified (01–09)**, followed by full release certification. Do not mark phases 05–09 complete merely to hit the target.
9. Implement and commit to **`origin/main`** without owner interaction once the intended code changes are coherent. Before committing, verify the current branch/head, inspect the diff and make sure no concurrent changes are overwritten. Avoid force pushes. Do not use destructive database backfills or hide failures.
10. Maintain `docs/SUITE_IMPLEMENTATION_TODO.md` and this handoff when material progress changes. Separate status: *implemented*, *locally tested*, *PostgreSQL verified*, *browser verified*, *provider/hardware verified*, *production certified*.
11. Preserve the independent standalone retail/supermarket experience and hotel/bar/restaurant deployments. Never reveal unrelated business modes in a customer's UI.
12. For historical financial data, provide read-only reconciliation and explicit correction policies; do not silently change money, vouchers, stock or audit entries.

## Working order

- Start by examining `git status`, `git log -5 --oneline`, the current tests, recent GitHub Actions failures and the phase checklist.
- Stabilize CI first, using actual failing test tracebacks. Fix application defects rather than changing assertions to hide behavior. Run relevant focused tests and then the full suite.
- Continue Phases 05–09 end-to-end (customer identity/privacy/invoices; loyalty/redemption/coupons; inventory intelligence; FEFO/batches/returns; supplier purchasing/credits), following dependencies and avoiding duplicates.
- Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and `python -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp` from `backend/` with dependencies installed. Inspect `.github/workflows/quality.yml` for the exact CI environment.
- Do not claim release certification without commit-bound PostgreSQL/RLS/concurrency, browser, hardware/provider where relevant, backup/restore, rollback and deployment evidence; follow `docs/RELEASE_CERTIFICATION.md`.

## Safety and escalation

Autonomous implementation is authorized, not fabrication of evidence. Record blockers precisely rather than granting yourself passing status. Do not fabricate external EFRIS credentials, real printer/device confirmation, financial accounting assumptions or user-approved license policy. Keep tests and deployment safe against live customers and payments.
