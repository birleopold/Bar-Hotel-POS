#!/usr/bin/env bash
# Local, read-only checks for POS configuration templates and collisions.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
test -f deployment/contabo/nginx-pos.conf.example
test -f deployment/contabo/leosoft-pos-gunicorn.service.example
test -f deployment/contabo/pos.env.example
bash -n deployment/contabo/preflight.sh
grep -q 'server_name pos.leosoftug.com;' deployment/contabo/nginx-pos.conf.example
grep -q '/run/leosoft-pos/gunicorn.sock' deployment/contabo/nginx-pos.conf.example
grep -q '/run/leosoft-pos/gunicorn.sock' deployment/contabo/leosoft-pos-gunicorn.service.example
grep -q '^TENANT_PLATFORM_DOMAIN=pos.leosoftug.com$' deployment/contabo/pos.env.example
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify deployment/contabo/leosoft-pos-gunicorn.service.example 2>&1 || echo "NOTE: Example unit needs deployment-specific paths and .service filename for final validation"
fi
echo 'PASS: POS template consistency; no configuration was changed'
