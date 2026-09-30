# Bar Hotel POS

Bar Hotel POS is a multi-tenant business operations platform for hospitality, food service, retail, and mixed-use venues. One workspace can manage hotels and lodges, restaurants, bars, supermarkets, services, event venues, stock, purchasing, finance, and staff access across multiple branches and sections.

The application is built with Django and server-rendered templates. Its responsive operations workspace and administration console use permission-aware left navigation on desktop and compact navigation on mobile.

## What the platform covers

| Area | Current capabilities |
| --- | --- |
| Restaurant and bar | Orders and tabs, tables, item modifiers, promotions, partial payments, refunds, shift close, preparation queue, recipes, and outlet-specific menus |
| Supermarket and retail | Barcode-aware catalog, weighted SKU configuration, checkout, line returns, stock balances, transfers, stock counts, suppliers, purchase orders, and partial goods receiving |
| Hotel and lodging | Reservations, availability, tape chart, check-in and checkout, room status, housekeeping, maintenance requests, folios, charges, payments, and nightly rate windows |
| Events and services | Event spaces, bookings, weekly calendar, services, and service packages |
| Finance and reporting | Sales summaries, section splits, income and expenses, automatic posting links, daily operations digest, and audit history |
| Administration | Multi-workspace access, branches, sections, staff roles, invites, module policies, branding, subscriptions, integrations, and guided setup |
| Uganda readiness | UGX-friendly operations, configurable tax data, and an optional EFRIS submission queue and integration registry |

## Product structure

- **Workspace:** the complete business account.
- **Branch:** a physical property or location.
- **Section:** an operational outlet such as a bar, restaurant, supermarket, kitchen, front desk, spa, or store.
- **Workstation:** the till or device used by staff.

Permissions, reporting, and operational visibility are scoped through this hierarchy.

## Technology

- Python and Django 5
- Django REST Framework and JWT authentication
- Django templates and Bootstrap 5
- SQLite for local development
- PostgreSQL with optional row-level security for production
- Redis, Django Channels, and Celery when asynchronous or realtime infrastructure is configured
- drf-spectacular for OpenAPI schema generation
- pytest and Django TestCase coverage

## Quick start

```powershell
git clone https://github.com/birleopold/Bar-Hotel-POS.git
cd Bar-Hotel-POS\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open:

- Staff sign-in: `http://127.0.0.1:8000/staff/login/`
- Operations workspace: `http://127.0.0.1:8000/staff/`
- Administration console: `http://127.0.0.1:8000/console/`
- API schema: `http://127.0.0.1:8000/api/v1/schema/swagger-ui/`

Local development uses SQLite when `DATABASE_URL` is not set. See [Installation](docs/INSTALLATION.md) for PostgreSQL and environment configuration.

## Validation

```powershell
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp
```

The September 30 exception-centre and shift-ledger checkpoint completed with **317 passing tests and 5 PostgreSQL-only skips**. See [the full suite checklist](docs/SUITE_IMPLEMENTATION_TODO.md) for tracked work and verification limits. These checks establish source and local application correctness; they do not prove a production deployment, external EFRIS acceptance, or physical device behavior.

## Documentation

### Run and maintain

- [Installation and local setup](docs/INSTALLATION.md)
- [Production deployment](docs/DEPLOYMENT.md)
- [Operations runbook](docs/OPERATIONS.md)
- [Security policy and production checklist](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

### Architecture and product

- [Architecture and API outline](docs/ARCHITECTURE.md)
- [Uganda platform overview](docs/PLATFORM_OVERVIEW_UGANDA.md)
- [Multi-vertical operations reference](docs/MULTI_VERTICAL_OPERATIONS_REFERENCE.md)
- [Supermarket POS capability and gap analysis](docs/SUPERMARKET_POS_GAP_ANALYSIS.md)
- [Product requirements](docs/PRODUCT_REQUIREMENTS_UGANDA.md)
- [Hospitality SaaS product plan](docs/HOSPITALITY_SAAS_PRODUCT_PLAN.md)
- [Staff and API parity](docs/STAFF_API_PARITY.md)
- [UI terminology guide](docs/UI_TERMINOLOGY_GUIDE.md)

### Audit and compliance

- [Systems audit](docs/SYSTEMS_AUDIT.md)
- [Audit recommendations](docs/AUDIT_RECOMMENDATIONS.md)
- [EFRIS compliance posture](docs/COMPLIANCE_EFRIS_POSTURE.md)
- [Executive summary](docs/EXECUTIVE_SUMMARY_UGANDA.md)

## Repository layout

```text
backend/
  apps/                 Django domain applications
  config/               Settings, URLs, ASGI, WSGI, and Celery configuration
  templates/            Shared templates
  tests/                Cross-domain regression tests
  manage.py
  requirements.txt
docs/                    Architecture, product, operations, and compliance documents
```

## License

No open-source license has been granted yet. Until a license is added, the repository remains copyright-protected and reuse requires the owner's permission.
