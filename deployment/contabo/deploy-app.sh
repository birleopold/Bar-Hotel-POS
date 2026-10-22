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
psql "$MIGRATION_DATABASE_URL" -X -v ON_ERROR_STOP=1 <<'SQL'
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO leosoft_pos_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO leosoft_pos_app;
SQL
"$VENV/bin/python" manage.py collectstatic --noinput
sudo install -d -o admin -g www-data -m 0755 /var/www/leosoft-pos/static
sudo rsync -a --delete "$APP/backend/staticfiles/" /var/www/leosoft-pos/static/
sudo chmod -R a+rX /var/www/leosoft-pos/static
# Critical Fizo CSS must exist in BOTH Django's output and nginx/Caddy's
# publicly served tree. A successful git pull alone cannot validate styling.
for asset in staff/fizo-setup-area.css staff/fizo-setup-wizard.css; do
  source_asset="$APP/backend/staticfiles/$asset"
  published_asset="/var/www/leosoft-pos/static/$asset"
  test -s "$source_asset" || { echo "ERROR: collectstatic missing $source_asset" >&2; exit 1; }
  test -s "$published_asset" || { echo "ERROR: public static file missing $published_asset" >&2; exit 1; }
  cmp -s "$source_asset" "$published_asset" || { echo "ERROR: published CSS differs: $asset" >&2; exit 1; }
  echo "Fizo CSS verified on disk: $asset"
done
sudo systemctl restart "$SERVICE"
sudo systemctl is-active --quiet "$SERVICE"
# Verify the public virtual host too. A different nginx alias or a proxy
# can serve old/404 CSS despite collectstatic being correct.
PUBLIC_ORIGIN="${POS_PUBLIC_ORIGIN:-https://fizo.pos.leosoftug.com}"
PUBLIC_ORIGIN="${PUBLIC_ORIGIN%/}"
for asset in staff/fizo-setup-area.css staff/fizo-setup-wizard.css; do
  public_url="$PUBLIC_ORIGIN/static/$asset"
  status="$(curl -L -sS -o /dev/null -w '%{http_code}' --max-time 15 "$public_url")"
  if [[ "$status" != "200" ]]; then
    echo "ERROR: Fizo CSS returned HTTP $status: $public_url" >&2
    echo "Inspect the nginx/Caddy static alias for $PUBLIC_ORIGIN" >&2
    exit 1
  fi
  echo "Fizo CSS served successfully: $public_url"
done
echo "POS deploy completed at $(git -C "$APP" rev-parse --short HEAD); check HTTPS and other applications before calling it certified."
