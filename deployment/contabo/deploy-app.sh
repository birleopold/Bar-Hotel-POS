#!/usr/bin/env bash
# POS-only repeatable deploy. Does not edit nginx, other services, or databases.
set -Eeuo pipefail
APP=/home/admin/Bar-Hotel-POS
VENV="$APP/.venv"
ENVFILE=/etc/leosoft-pos/pos.env
SERVICE=leosoft-pos-gunicorn.service
cd "$APP"
test "$(id -un)" = admin || { echo 'Run as admin, not root'; exit 1; }
test -f "$ENVFILE" || { echo "Missing $ENVFILE"; exit 1; }
test -d .git || { echo "Not a git checkout: $APP"; exit 1; }
test -z "$(git status --porcelain)" || { echo "Local modifications: stop before pull"; exit 1; }
git checkout main
git pull --ff-only origin main
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -r backend/requirements.txt
# Read keys from service env. It must contain shell-compatible KEY=value lines
# (no unquoted whitespace and no command substitution).
set -a
source "$ENVFILE"
set +a
export DJANGO_SETTINGS_MODULE=config.settings.production
cd backend
"$VENV/bin/python" manage.py check --deploy
"$VENV/bin/python" manage.py makemigrations --check --dry-run
if [[ -z "${MIGRATION_DATABASE_URL:-}" ]]; then
  echo 'MIGRATION_DATABASE_URL must be set to a separate DB-owner connection for schema migrations.' >&2
  exit 1
fi
DATABASE_URL="$MIGRATION_DATABASE_URL" "$VENV/bin/python" manage.py migrate --noinput
# Newly created tables/sequences must be readable by the separate non-owner runtime role.
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 \\
  -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO leosoft_pos_app" \\
  -c "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO leosoft_pos_app"
"$VENV/bin/python" manage.py collectstatic --noinput
sudo install -d -o admin -g www-data -m 0755 /var/www/leosoft-pos/static
sudo rsync -a --delete "$APP/backend/staticfiles/" /var/www/leosoft-pos/static/
sudo chmod -R a+rX /var/www/leosoft-pos/static
sudo systemctl restart "$SERVICE"
sudo systemctl is-active --quiet "$SERVICE"
echo "POS deploy completed at $(git -C "$APP" rev-parse --short HEAD); check HTTPS and other applications before calling it certified."
