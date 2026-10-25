# POS on shared Contabo Ubuntu 24.04 VPS

**Target:** `https://pos.leosoftug.com`. Customer workspace addresses:
`{tenant}.pos.leosoftug.com` and separately verified apex/custom hostnames.

**Never run commands blindly on the existing multi-app VPS.** First inventory
current nginx sites, active systemd units, occupied ports, PostgreSQL clusters,
SSL renewal and backup jobs. This setup must not stop or replace other Django apps.

## Isolation contract

- Use your existing unprivileged `admin` account, but keep POS isolated in
  `/home/admin/Bar-Hotel-POS` and `/home/admin/Bar-Hotel-POS/.venv`. The POS
  still gets its own systemd unit, Unix socket, PostgreSQL roles/database and
  static-files directory `/var/www/leosoft-pos/static`.
- POS-only PostgreSQL database, login role, schema ownership strategy and
  independent backups. **Important:** production POS app role must not be
  superuser, have BYPASSRLS, or own RLS-protected tables.
- Dedicated systemd unit `leosoft-pos-gunicorn.service` and an isolated Unix
  socket or free localhost port; preserve other app units.
- Dedicated `pos.leosoftug.com` nginx server block; modify no other
  `server_name`. Route tenant subdomains using a validated wildcard host,
  configured DNS wildcard A/AAAA and wildcard TLS cert. Do not assume
  Let's Encrypt's HTTP challenge issues wildcard certificates; configure DNS-01.
- Independently verified custom domains require TXT ownership proof, correct
  A/AAAA/CNAME record as appropriate, `ALLOWED_HOSTS` admission and valid
  hostname-specific HTTPS certificates **before** activating the domain.
- Keep CSRF and session cookies host-only by default; never share a cookie
  domain across customers. Limit trusted proxy headers to the local nginx
  instance and deny unrecognised hosts at nginx and Django.
- Avoid applying HSTS to a broader parent domain owned by other services.
  Specifically, do not redirect or change `leosoftug.com`, `hotspotcloud.net`,
  or any unrelated nginx virtual host.

## Read-only preflight

From the checked-out repository root on the VPS:

```bash
bash deployment/contabo/preflight.sh
```

This command inventories the current OS, nginx validity, app services,
listening ports and DNS/HTTPS readiness. It **does not make changes**.

## Service template

`leosoft-pos-gunicorn.service.example` is an example of a dedicated Gunicorn
systemd unit for the POS. Review directory permissions and worker counts before
installing it. Do **not** copy it over an existing service or issue a blanket
`systemctl restart gunicorn`. Keep the POS Unix socket independent from every
other application and make sure nginx alone can reach it.

The `ProtectSystem` and `ReadWritePaths` restrictions are starting points;
adjust them to actual upload, log, cache and backup storage locations without
granting the POS access to unrelated application directories.

## Dedicated Nginx configuration

The example `nginx-pos.conf.example` uses the POS Unix socket and a
`pos.leosoftug.com`-only server block. Before installing it, issue the
hostname-specific TLS certificate, configure the POS static-files directory
and ensure no existing vhost owns the same `server_name`. Validate with
`sudo nginx -t` **before** any POS-only reload.

For platform workspace subdomains, use a separately reviewed wildcard vhost
with DNS-01-issued wildcard TLS and correctly configured wildcard DNS;
customer-owned domains each need ownership verification and an independently
valid certificate. Do not widen the central vhost to arbitrary hostnames.

From a checked-out repository, run `bash deployment/contabo/validate-config.sh`
to check template consistency without changing the machine.

## Production env

Use `pos.env.example` as a checklist and store the runtime environment at
`/etc/leosoft-pos/pos.env`. During the current development/acceptance stage,
`deploy-app.sh` uses the existing application `DATABASE_URL` directly for
Django migrations, matching the simpler deployment style used by the other
applications on this VPS. No separate `MIGRATION_DATABASE_URL` prompt is
required.

Before final production hardening, review the PostgreSQL ownership/RLS model
again and restore a dedicated migration-owner path if required. Do not expose
`/home/admin` through the web server; POS static assets are published under
`/var/www/leosoft-pos/static`.

## W3 acceptance (non-destructive)

1. Verify PostgreSQL migrations and all tenant policies in a disposable DB.
2. Test reads/writes with an app role **subject to** row level security,
   including no tenant GUC and a foreign tenant GUC.
3. Verify Django API, staff routes, queue workers, exports, sessions and
   cross-domain identities for separate business tenants.
4. Establish DB restore procedure, least-privilege POS app role and audit logs.

## W4 acceptance (requires live VPS/browser)

1. Verify central host login and TLS on `pos.leosoftug.com`.
2. Verify one reserved platform subdomain and one verified custom domain,
   including TXT ownership challenge, issuance/renewal and host resolution.
3. Test supermarket, bar, restaurant, hotel and mixed-business staff flows
   on mobile/tablet/desktop, including PIN handover, receipts and print margins.
4. Check that existing VPS Django sites still respond and their systemd units,
   sockets, PostgreSQL databases and certificates are unchanged.
5. Rehearse rollback and database restore before production sign-off.

**Status:** deployment is *not* performed by these repository files; no DNS,
VPS, certificate or browser acceptance is implied.
