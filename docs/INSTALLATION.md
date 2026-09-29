# Installation and local development

## Prerequisites

- Python 3.12 or newer
- Git
- PostgreSQL 15+ for production-like tenancy testing, or SQLite for local development
- Redis when testing Channels, Celery workers, or shared caching

## Windows setup

```powershell
git clone https://github.com/birleopold/Bar-Hotel-POS.git
cd Bar-Hotel-POS\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## macOS or Linux setup

```bash
git clone https://github.com/birleopold/Bar-Hotel-POS.git
cd Bar-Hotel-POS/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Environment configuration

The example file is [`backend/.env.example`](../backend/.env.example). At minimum, production requires a strong `SECRET_KEY`, `DEBUG=False`, allowed hosts, trusted CSRF origins, and a PostgreSQL `DATABASE_URL`.

Local SQLite configuration:

```env
SECRET_KEY=local-development-only
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

PostgreSQL example:

```env
DATABASE_URL=postgres://bar_hotel_pos:change-me@127.0.0.1:5432/bar_hotel_pos
POSTGRES_SET_REQUEST_TENANT_GUC=true
```

Optional Redis and Celery configuration:

```env
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_TASK_ALWAYS_EAGER=False
```

## First workspace

1. Sign in at `/staff/login/` with the superuser.
2. Open `/console/`.
3. Create or select a workspace.
4. Follow the guided setup to create a branch and its sections.
5. Configure the required catalogs, rooms, services, and staff members.
6. Return to `/staff/` for daily operations.

## Tests and checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp
```

Use a writable `--basetemp` on managed Windows systems if pytest reports a temporary-directory permission error.

## API access

Session authentication is used by the server-rendered staff and console interfaces. API clients obtain JWT tokens from `/api/v1/auth/token/` and send tenant context only through the documented, membership-validated flow. Do not treat a client-supplied tenant identifier as authorization.
