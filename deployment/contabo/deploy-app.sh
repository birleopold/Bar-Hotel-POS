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

DB_NAME="$(psql "$DATABASE_URL" -X -A -t -v ON_ERROR_STOP=1 -c 'SELECT current_database()')"
APP_ROLE="$(psql "$DATABASE_URL" -X -A -t -v ON_ERROR_STOP=1 -c 'SELECT current_user')"
DB_OWNER="$(sudo -u postgres psql -d "$DB_NAME" -X -A -t -v ON_ERROR_STOP=1 -c 'SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()')"

if [[ -z "$DB_NAME" || -z "$APP_ROLE" || -z "$DB_OWNER" ||
      ! "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ||
      ! "$APP_ROLE" =~ ^[A-Za-z0-9_]+$ ||
      ! "$DB_OWNER" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "Unable to resolve safe PostgreSQL names for automatic migration." >&2
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
