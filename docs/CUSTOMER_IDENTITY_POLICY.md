# Customer and guest identity operating policy

This document covers the shared customer identity used in the bar, restaurant,
retail, lodging and events workflows. It does **not** authorize unverified merges,
new credit, tax invoices or automatic deletion of financial history.

## Creating or linking identities

- Use Customers & guests to search for an existing visible person before creating another profile.
- A phone or email match is only a duplicate warning, **not proof** that two people are identical.
- Local and international phone numbers retain their typed prefix; separators are normalized for newly saved staff records. Historic contacts are not silently rewritten.
- Staff may see customers linked to their permitted stays, orders, outlets or events. Ownership of a new unlinked entry does not automatically override branch privacy.
- For an unlinked profile created by restricted staff, an authorized manager must associate a permitted operational record before that employee can open it.
- Customer linking is explicit; historical names on orders, reservations and event records remain snapshots.

## Merging and financial records

- Only authorized owners or tenant administrators may merge two active customer identities within the **same tenant**, after verifying identity and documenting a reason.
- The merge redirects linked records but does not change original amounts, bill references, guest-name snapshots or original financial postings. No merge should be inferred from matching email or phone.
- Customer financial summaries show direct paid POS sales, actual POS refunds and net direct POS sales separately. Folio-linked POS orders belong to folio charges and are not counted again as standalone receipts.
- Folio outstanding amounts are charges less payments, displayed **by original currency**, not converted into a single balance. Negative folio balances and points are review signals, not automatic money credit.
- A folio is a guest-account record, not automatically a tax-approved invoice. Do not print or label a fiscal invoice until the relevant legal and integration requirements have been satisfied.

## Access, retention and correction

- Use the existing role, tenant, branch and outlet permissions for all customer lookups, including the read-only REST directory.
- Customer API access is read-only. Customer changes and merges remain attributed through the staff/domain workflows.
- Keep records and immutable operational/financial history according to applicable legal retention periods and the tenant's adopted privacy policy. This system does **not** yet automate erasure, anonymization or full data-subject export.
- Any request to correct or erase personal data must be reviewed separately from accounting record retention; do not delete order, folio, receipt, event or loyalty evidence to hide an incorrect identity.
- Before deploying, verify tenant scoping and PostgreSQL row-level policies, protected exports, mobile browser behavior and simultaneous order/merge operations on a disposable production-like environment.

## Acceptance checklist

Locally: run the full automated suite plus customer visibility, shared identity,
finance snapshot, merge and read-only API tests. Verify forms visibly display
non-field errors. Never count a green SQLite build as PostgreSQL or browser
certification. Operational sign-off requires the specific privacy policy,
invoice/tax classification and retention requirements of the deploying business.
