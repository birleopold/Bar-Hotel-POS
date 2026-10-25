#!/usr/bin/env bash
# Simple POS deploy for the current development/acceptance stage.
# Uses the application's existing DATABASE_URL for migrations; no second DB login.
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
"$VENV/bin/python" manage.py migrate --noinput
"$VENV/bin/python" manage.py collectstatic --noinput

sudo install -d -o admin -g www-data -m 0755 /var/www/leosoft-pos/static
sudo rsync -a --delete "$APP/backend/staticfiles/" /var/www/leosoft-pos/static/
sudo chmod -R a+rX /var/www/leosoft-pos/static

sudo systemctl restart "$SERVICE"
sudo systemctl is-active --quiet "$SERVICE"

echo "POS deploy completed at $(git -C "$APP" rev-parse --short HEAD)."
