# Production deployment

This guide describes the production boundary. A successful Git push or local test run does not establish that a deployment, database migration, EFRIS submission, payment provider, or physical workstation is functioning.

## Required services

- Django ASGI application served by Daphne or another production ASGI server
- PostgreSQL
- Redis for production Channels, caching, and Celery
- Celery worker and scheduler when background queues are enabled
- TLS-terminating reverse proxy or managed application platform
- Durable log collection, error monitoring, and database backups

## Required environment

```env
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=<strong-random-secret>
DEBUG=False
ALLOWED_HOSTS=pos.example.com
CSRF_TRUSTED_ORIGINS=https://pos.example.com
DATABASE_URL=postgres://...
REDIS_URL=redis://...
CELERY_BROKER_URL=redis://...
CELERY_TASK_ALWAYS_EAGER=False
POSTGRES_SET_REQUEST_TENANT_GUC=true
USE_X_FORWARDED_PROTO=true
```

Keep provider credentials in a secrets manager. Never commit `.env`, database files, API keys, access tokens, EFRIS secrets, payment credentials, or exported customer data.

## Release sequence

1. Build an immutable release from a reviewed commit.
2. Install pinned or reviewed dependencies.
3. Run `python manage.py check --deploy` using production settings.
4. Back up the database and verify restore procedures.
5. Run `python manage.py migrate` once per release.
6. Run `python manage.py collectstatic --noinput`.
7. Start or roll application instances.
8. Start Celery workers and the scheduler when enabled.
9. Verify health, login, tenant selection, and representative read-only screens.
10. Perform authorized smoke transactions in each enabled business sector.

Example processes from the `backend` directory:

```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
celery -A config worker -l info
celery -A config beat -l info
```

## PostgreSQL tenancy

PostgreSQL migrations install row-level security policies for supported tenant-scoped tables. The application still applies explicit tenant filters. Use a restricted application database role and verify that the request tenant GUC is set only after authenticated membership resolution.

Test tenant isolation in the deployed environment before importing production data.

## Static assets and proxying

- Serve collected static assets from a CDN, object store, or reverse proxy.
- Forward the original protocol only through a trusted proxy.
- Enforce HTTPS and secure cookies.
- Apply upload size limits and request timeouts appropriate to CSV imports and exports.
- Preserve WebSocket upgrade headers if realtime features are enabled.

## Deployment verification

Verify these separately:

- application revision matches the intended commit;
- migrations are applied;
- static assets load without mixed-content or cache errors;
- staff and console permission boundaries hold;
- each configured outlet shows only its enabled modules;
- orders, payments, refunds, and shift close reconcile;
- purchasing receipts update stock once and remain auditable;
- reservations, folios, payments, and checkout reconcile;
- backups can be restored;
- EFRIS or other providers accept a controlled test only when credentials and legal approval are available.

## Rollback

Application rollback and database rollback are separate decisions. Prefer forward-fixing schema migrations. Before reverting application code, confirm it remains compatible with the migrated schema. Restore a database only under an incident plan that accounts for transactions created after the backup.
