#!/usr/bin/env bash
# Publish only Fizo login stylesheet while a DB migration awaits authorization.
# Does not restart Django, apply migrations, or touch credentials.
set -Eeuo pipefail
APP=/home/admin/Bar-Hotel-POS
ASSET=staff/fizo-auth-2026.css
SOURCE="$APP/backend/apps/staff/static/$ASSET"
DEST="/var/www/leosoft-pos/static/$ASSET"
test "$(id -un)" = admin || { echo "Run as admin, not root" >&2; exit 1; }
test -s "$SOURCE" || { echo "Missing login CSS: $SOURCE" >&2; exit 1; }
sudo install -d -m 0755 /var/www/leosoft-pos/static/staff
sudo install -m 0644 "$SOURCE" "$DEST"
sudo chmod a+rx /var/www/leosoft-pos/static /var/www/leosoft-pos/static/staff
cmp -s "$SOURCE" "$DEST" || { echo "CSS differs on disk" >&2; exit 1; }
for host in fizo.pos.leosoftug.com pos.leosoftug.com; do
  tmp="$(mktemp)"
  status="$(curl -sSL --max-time 20 -o "$tmp" -w '%{http_code}' "https://$host/static/$ASSET")"
  if [[ "$status" != 200 ]]; then
    echo "ERROR: $host returned HTTP $status for /static/$ASSET" >&2
    rm -f "$tmp"
    exit 1
  fi
  cmp -s "$SOURCE" "$tmp" || {
    echo "ERROR: $host serves different CSS; inspect virtual host static alias" >&2
    rm -f "$tmp"
    exit 1
  }
  rm -f "$tmp"
  echo "Verified CSS on https://$host/static/$ASSET"
done
echo "Login CSS published; Django migration is still pending."
echo "If HTML still uses a relative URL, complete normal migration/deployment to reload login templates."
