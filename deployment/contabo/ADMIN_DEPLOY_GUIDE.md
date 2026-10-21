# Deployment as admin on existing Ubuntu 24.04 VPS

The POS has a separate Git checkout, virtualenv, database, Gunicorn unit, socket,
Nginx vhost, and static directory. Do not change unrelated services.

## A. Inspect and clone

```bash
ssh admin@158.220.114.219
sudo nginx -t
sudo systemctl --type=service --state=running --no-pager | grep -Ei 'gunicorn|hotspot|leosoft|edumanage' || true
sudo ss -ltnp | grep -E ':(80|443|5432)\\b' || true
cd /home/admin
git clone https://github.com/birleopold/Bar-Hotel-POS.git
cd Bar-Hotel-POS
bash deployment/contabo/preflight.sh
bash deployment/contabo/validate-config.sh
```

If already cloned: `cd /home/admin/Bar-Hotel-POS && git pull --ff-only origin main`.

## B. PostgreSQL (two isolated roles)

Create POS-only database `leosoft_pos`, schema owner `leosoft_pos_owner`
and runtime login `leosoft_pos_app` with **different strong passwords**.
Never reuse other Django databases. Use `sudo -u postgres psql` and run,
replacing the password placeholders:

```sql
CREATE ROLE leosoft_pos_owner LOGIN PASSWORD 'SET_UNIQUE_OWNER_PASSWORD';
CREATE ROLE leosoft_pos_app LOGIN PASSWORD 'SET_UNIQUE_APP_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE DATABASE leosoft_pos OWNER leosoft_pos_owner;
```

Database creation must run outside a transaction. Connect to the POS DB:
`sudo -u postgres psql -d leosoft_pos` and run:

```sql
GRANT CONNECT ON DATABASE leosoft_pos TO leosoft_pos_app;
GRANT USAGE ON SCHEMA public TO leosoft_pos_app;
ALTER DEFAULT PRIVILEGES FOR ROLE leosoft_pos_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO leosoft_pos_app;
ALTER DEFAULT PRIVILEGES FOR ROLE leosoft_pos_owner IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO leosoft_pos_app;
```

After first migrations also run:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO leosoft_pos_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO leosoft_pos_app;
```

**Important:** the Django runtime role must not own the tables, have
`BYPASSRLS`, or be a superuser. Run migrations with the owner connection;
normal Gunicorn requests use the runtime app connection.

## C. Runtime environment and software

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev libpq-dev build-essential rsync
sudo install -d -o admin -g admin -m 0700 /etc/leosoft-pos
sudo install -o admin -g admin -m 0600 deployment/contabo/pos.env.example /etc/leosoft-pos/pos.env
nano /etc/leosoft-pos/pos.env
```

Set `SECRET_KEY` (generate with `python3 -c 'import secrets; print(secrets.token_urlsafe(64))'`),
`DATABASE_URL` for `leosoft_pos_app`, and confirm
`TENANT_PLATFORM_DOMAIN=pos.leosoftug.com` and other fields. Keep
`MIGRATION_DATABASE_URL` out of this long-lived file. Ensure all values use
shell-compatible `KEY=value` syntax without spaces or shell metacharacters.

## D. Migrate and start POS only

Create the POS unit after reviewing the template:

```bash
sudo cp deployment/contabo/leosoft-pos-gunicorn.service.example /etc/systemd/system/leosoft-pos-gunicorn.service
sudo systemctl daemon-reload
```

Supply the temporary migration owner's DB URL only in the current terminal:

```bash
read -rsp 'POS schema-owner PostgreSQL password: ' OWNER_PW; echo
export MIGRATION_DATABASE_URL="postgresql://leosoft_pos_owner:${OWNER_PW}@127.0.0.1:5432/leosoft_pos"
unset OWNER_PW
bash deployment/contabo/deploy-app.sh
unset MIGRATION_DATABASE_URL
```

The deploy script runs the two post-migration runtime-role `GRANT` statements
before restarting Gunicorn. Those privileges are confined to `leosoft_pos`.
If it stops, inspect the error; do not restart unrelated applications.

Check: `sudo systemctl status leosoft-pos-gunicorn.service --no-pager`
and `sudo journalctl -u leosoft-pos-gunicorn.service -n 80 --no-pager`.

## E. Nginx / certificates (separate staging)

Do **not** enable `nginx-pos.conf.example` before the hostname certificate
exists. Use the POS-only HTTP challenge vhost first, without replacing any
existing sites. These commands assume `pos.leosoftug.com` already resolves
correctly and no existing nginx site claims that same hostname:

```bash
sudo apt-get install -y certbot
sudo install -d -m 0755 /var/www/leosoft-pos/acme/.well-known/acme-challenge
sudo cp deployment/contabo/nginx-pos-http.conf.example /etc/nginx/sites-available/leosoft-pos.conf
sudo ln -s /etc/nginx/sites-available/leosoft-pos.conf /etc/nginx/sites-enabled/leosoft-pos.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/leosoft-pos/acme -d pos.leosoftug.com
sudo cp deployment/contabo/nginx-pos.conf.example /etc/nginx/sites-available/leosoft-pos.conf
```

The final POS-only nginx template preserves the HTTP-01 ACME path for later
renewals. Always run `nginx -t` before reloading. Confirm:

```bash
sudo nginx -t
sudo systemctl reload nginx
curl -I https://pos.leosoftug.com/
```

The wildcard customer subdomain certificate for
`*.pos.leosoftug.com` requires DNS-01, not an A record or HTTP-01.
If using manual TXT challenges, renewal is **not automatic**. Plan automated
DNS renewal before opening tenants to production. Never route unverified
custom domains to tenant sessions.

## F. W3/W4 release check

Confirm SQLite/Postgres GitHub CI, isolated runtime database role and absence
of cross-tenant reads, PIN user handoff, receipts, all business profiles,
and HTTPS on the main/wildcard/custom tenant domains. Check that other Django
units and sites still respond, and verify database backup/restore and rollback.

These steps are a reviewed deployment recipe, **not evidence of VPS deployment**.
