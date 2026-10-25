#!/usr/bin/env bash
# Simple POS deploy for the current development/acceptance stage.
# No second database login: migrations temporarily inherit the local DB owner.
set -Eeuo pipefail

APP=/home/admin/Bar-Hotel-POS
VENV="$APP/.venv"
ENVFILE=/etc/leosoft-pos/pos.env
SERVICE=leosoft-pos-gunicorn.service

cd "$APP"
git checkout main
git pull --ff-only origin main

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -r backend/requirements.txt

set -a
source "$ENVFILE"
set +a
export DJANGO_SETTINGS_MODULE=config.settings.production

cd "$APP/backend"

mapfile -t DB_PARTS < <("$VENV/bin/python" - <<'PY'
import django
django.setup()
from django.conf import settings

db = settings.DATABASES["default"]
print(str(db.get("NAME") or ""))
print(str(db.get("USER") or ""))
PY
)

DB_NAME="${DB_PARTS[0]:-}"
APP_ROLE="${DB_PARTS[1]:-}"

if [[ -z "$DB_NAME" || -z "$APP_ROLE" ||
      ! "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ||
      ! "$APP_ROLE" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "Unable to resolve safe PostgreSQL database/user settings from Django." >&2
  exit 1
fi

DB_OWNER="$(sudo -u postgres psql -d "$DB_NAME" -X -A -t -v ON_ERROR_STOP=1 \
  -c 'SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()')"
if [[ -z "$DB_OWNER" || ! "$DB_OWNER" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "Unable to resolve a safe PostgreSQL database owner." >&2
  exit 1
fi

ROLE_ELEVATED=0
restore_db_role() {
  if [[ "$ROLE_ELEVATED" == "1" ]]; then
    sudo -u postgres psql -d "$DB_NAME" -X -v ON_ERROR_STOP=1 \
      -c "REVOKE \"$DB_OWNER\" FROM \"$APP_ROLE\"; ALTER ROLE \"$APP_ROLE\" NOINHERIT;" >/dev/null || true
    ROLE_ELEVATED=0
  fi
}
trap restore_db_role EXIT

if [[ "$APP_ROLE" != "$DB_OWNER" ]]; then
  sudo systemctl stop "$SERVICE" || true
  sudo -u postgres psql -d "$DB_NAME" -X -v ON_ERROR_STOP=1 \
    -c "ALTER ROLE \"$APP_ROLE\" INHERIT; GRANT \"$DB_OWNER\" TO \"$APP_ROLE\";" >/dev/null
  ROLE_ELEVATED=1
fi

"$VENV/bin/python" manage.py migrate --noinput
restore_db_role
trap - EXIT

"$VENV/bin/python" manage.py collectstatic --noinput

sudo install -d -o admin -g www-data -m 0755 /var/www/leosoft-pos/static
sudo rsync -a --delete "$APP/backend/staticfiles/" /var/www/leosoft-pos/static/
sudo chmod -R a+rX /var/www/leosoft-pos/static

sudo systemctl restart "$SERVICE"
sudo systemctl is-active --quiet "$SERVICE"

echo "POS deploy completed at $(git -C "$APP" rev-parse --short HEAD)."
