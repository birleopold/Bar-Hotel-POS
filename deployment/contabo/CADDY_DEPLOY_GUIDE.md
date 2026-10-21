# Actual VPS edge: Caddy controls :80/:443

Observed on Contabo Ubuntu 24.04: Caddy owns public ports 80/443.
Nginx is installed but **must not** be used for the POS public vhost.
Keep existing Caddy sites and Django services untouched.

## Read-only inventory (first)
```bash
sudo systemctl status caddy --no-pager
sudo caddy version
sudo caddy validate --config /etc/caddy/Caddyfile
sudo grep -nE 'import|leosoftug|hotspot|signalsolid|edumanage' /etc/caddy/Caddyfile
sudo ls -la /etc/caddy
sudo ss -ltnp | grep -E ':(80|443)\\b'
```
Only after examining those results, add a *new* Caddy site for the POS.
The example at `pos.Caddyfile.example` serves the central hostname.
Use `sudo caddy validate --config /etc/caddy/Caddyfile` prior to
`sudo systemctl reload caddy`. Never overwrite the entire active Caddyfile.

## Pos application
Existing Git checkout: `/home/admin/Bar-Hotel-POS`; venv:
`/home/admin/Bar-Hotel-POS/.venv`; service:
`leosoft-pos-gunicorn.service`; socket:
`/run/leosoft-pos/gunicorn.sock`.

The deployment script needs `/etc/leosoft-pos/pos.env` and two dedicated
PostgreSQL roles. Use the setup sequence in ADMIN_DEPLOY_GUIDE.md,
**excluding the Nginx and certbot sections**. Run POS systemd service before
routing Caddy to it. The Caddy user needs permission to access its Unix
socket; by default Caddy does not necessarily belong to `www-data`.
Either grant access through a dedicated system group, or bind Gunicorn on a
private unique port such as `127.0.0.1:18083` and proxy to that port.
Avoid port collisions.

## Customer domains and certificates
For central `pos.leosoftug.com`, Caddy can automatically issue the
normal certificate once DNS points here and port 80/443 is reachable.
For `*.pos.leosoftug.com`, a wildcard certificate requires DNS-01 and a
supported DNS provider module/credentials; a wildcard A record **does not**
issue a wildcard certificate. Do not enable wildcard HTTPS until verified.

This guide is not an execution confirmation. Production use also requires
dedicated database roles with non-owner RLS, tested migrations, a backup,
tenant-resolution smoke tests, and independent validation of current sites.
