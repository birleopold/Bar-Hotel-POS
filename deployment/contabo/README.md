# POS on shared Contabo Ubuntu 24.04 VPS

**Target:** `https://pos.leosoftug.com`. Customer workspace addresses:
`{tenant}.pos.leosoftug.com` and separately verified apex/custom hostnames.

**Never run commands blindly on the existing multi-app VPS.** First inventory
current nginx sites, active systemd units, occupied ports, PostgreSQL clusters,
SSL renewal and backup jobs. This setup must not stop or replace other Django apps.

## Isolation contract

- Keep this repository and virtualenv separate, e.g. `/srv/leosoft-pos/app`
  and `/srv/leosoft-pos/venv`; run as a dedicated unprivileged Linux user.
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

## Production env

Use `pos.env.example` as a checklist; provision secrets securely rather than
committing them. Application settings live in `backend/config/settings/production.py`.
The file deliberately does not enable HSTS for subdomains until their HTTPS
coverage is certified.

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
