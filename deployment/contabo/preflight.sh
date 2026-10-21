#!/usr/bin/env bash
# Read-only deployment preflight for the shared Contabo Ubuntu VPS.
# Does not edit nginx, systemd, PostgreSQL, DNS or certificates.
set -Eeuo pipefail

domain="${POS_DOMAIN:-pos.leosoftug.com}"
service="${POS_SERVICE:-leosoft-pos-gunicorn.service}"
socket="${POS_SOCKET:-/run/leosoft-pos/gunicorn.sock}"

failures=0
warn() { printf 'WARN: %s\n' "$*" >&2; }
pass() { printf 'PASS: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; failures=$((failures+1)); }

if [[ "$domain" != "pos.leosoftug.com" ]]; then
  warn "POS_DOMAIN differs from agreed central domain: $domain"
fi
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  if [[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == "24.04" ]]; then
    pass "Ubuntu 24.04 detected"
  else
    warn "Expected Ubuntu 24.04; detected ${PRETTY_NAME:-unknown}"
  fi
else
  warn "Unable to inspect operating system"
fi

for bin in nginx systemctl python3 psql; do
  if command -v "$bin" >/dev/null 2>&1; then pass "$bin available"; else warn "$bin not installed or not on PATH"; fi
done

if command -v nginx >/dev/null 2>&1; then
  if sudo -n nginx -t >/dev/null 2>&1; then pass "Existing nginx configuration valid"; else warn "Could not validate nginx (sudo permission or configuration issue)"; fi
fi

if command -v systemctl >/dev/null 2>&1; then
  printf '\nExisting web application units (inventory only):\n'
  systemctl list-units --all --type=service --no-pager --no-legend 2>/dev/null | grep -Ei 'gunicorn|uwsgi|django|celery|leosoft|hotspot' || true
  if systemctl is-active --quiet "$service"; then
    pass "POS service is active: $service"
  else
    warn "POS service is not active yet: $service"
  fi
fi

printf '\nExisting listening TCP ports (inventory only):\n'
if command -v ss >/dev/null 2>&1; then
  ss -ltn 2>/dev/null || true
fi

if [[ -S "$socket" ]]; then pass "POS socket exists: $socket"; else warn "POS socket not active yet: $socket"; fi

if command -v getent >/dev/null 2>&1; then
  if getent ahostsv4 "$domain" >/dev/null; then pass "Central domain resolves in DNS"; else warn "Central domain does not currently resolve"; fi
fi

if command -v curl >/dev/null 2>&1; then
  if curl --fail --silent --show-error --head --max-time 10 "https://$domain/" >/dev/null 2>&1; then
    pass "Central HTTPS endpoint responds successfully"
  else
    warn "Central HTTPS endpoint is not ready, or rejects HEAD"
  fi
fi

printf '\nNo system configuration was modified.\n'
if ((failures)); then exit 1; fi
