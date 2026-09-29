# Security policy

## Reporting a vulnerability

Do not open a public issue containing credentials, customer data, exploitable tenant identifiers, or reproduction details that expose a running system. Contact the repository owner privately with the affected revision, impact, and the smallest safe reproduction.

## Supported code

Security fixes target the current `main` branch unless the repository owner documents another supported release.

## Production security checklist

- Use `config.settings.production`.
- Set a strong unique `SECRET_KEY`; never use the development default.
- Set `DEBUG=False`.
- Restrict `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- Terminate TLS through a trusted proxy and use secure cookies.
- Use PostgreSQL with a restricted application role.
- Enable and verify tenant row-level security where supported.
- Resolve tenant identity from authenticated membership, then validate site and outlet scope.
- Store secrets in environment or a managed secrets service.
- Rotate provider credentials and remove unused integration links.
- Limit platform operator accounts and require strong authentication.
- Monitor failed authentication, permission denials, refunds, voids, stock adjustments, and role changes.
- Encrypt backups and test isolated restoration.

## Sensitive files

The repository ignores `.env`, virtual environments, SQLite databases, caches, and collected static files. Before committing, inspect staged changes for tokens, passwords, certificates, customer exports, database dumps, logs, and screenshots containing personal or financial data.

## Tenant isolation

Application query scoping and permission checks are mandatory even when PostgreSQL row-level security is enabled. API tenant headers are context hints and must never grant access by themselves. Cross-tenant platform operations require explicit platform authorization and separate review.

## External integrations

EFRIS, payment, email, and other provider success must be verified from signed or authoritative provider responses. Queue acceptance proves only that local work was scheduled.
