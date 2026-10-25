#!/usr/bin/env bash
# Local, read-only checks for POS configuration templates and collisions.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
test -f deployment/contabo/pos.Caddyfile.example
test -f deployment/contabo/leosoft-pos-gunicorn.service.example
test -f deployment/contabo/pos.env.example
bash -n deployment/contabo/preflight.sh
bash -n deployment/contabo/deploy-app.sh
grep -q 'manage.py migrate --noinput' deployment/contabo/deploy-app.sh
! grep -q 'MIGRATION_DATABASE_URL' deployment/contabo/deploy-app.sh
! grep -q 'psql "$DATABASE_URL"' deployment/contabo/deploy-app.sh
! grep -q 'PGPASSWORD=' deployment/contabo/deploy-app.sh
grep -q 'settings.DATABASES\["default"\]' deployment/contabo/deploy-app.sh
grep -q 'GRANT .*DB_OWNER.*APP_ROLE' deployment/contabo/deploy-app.sh
grep -q 'REVOKE .*DB_OWNER.*APP_ROLE' deployment/contabo/deploy-app.sh
grep -q '^pos.leosoftug.com {' deployment/contabo/pos.Caddyfile.example
grep -q 'reverse_proxy 127.0.0.1:18083' deployment/contabo/pos.Caddyfile.example
grep -q '\-\-bind 127.0.0.1:18083' deployment/contabo/leosoft-pos-gunicorn.service.example
grep -q '^TENANT_PLATFORM_DOMAIN=pos.leosoftug.com$' deployment/contabo/pos.env.example
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify deployment/contabo/leosoft-pos-gunicorn.service.example 2>&1 || echo "NOTE: Example unit needs deployment-specific paths and .service filename for final validation"
fi
echo 'PASS: POS template consistency; no configuration was changed'
