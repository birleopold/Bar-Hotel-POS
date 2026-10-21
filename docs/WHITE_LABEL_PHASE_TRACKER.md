# Tenant white-labelling release gate (21 October 2026)

**Policy:** Implemented, CI-verified, PostgreSQL-verified, and browser-certified are separate states. Do not mark W1/W2 production-complete until the acceptance journeys pass.

## W1 — Branding Studio

- [x] Tenant name, logo, three accent/theme colours, receipt footer and owner/admin-only editing.
- [x] Tenant-specific password/PIN sign-in branding, welcome message and HTTPS photo background.
- [x] Tenant-specific favicon, with logo fallback across staff chrome and login pages.
- [x] Live name, colour, logo, welcome-message and background preview.
- [x] Dedicated migration and cross-tenant branding regression tests.
- [ ] Verify the combined W1 changes pass **both** SQLite and PostgreSQL CI.
- [ ] Review every generated financial document and email notification for identity, sender and tenant-data isolation (not all use the order print template).
- [ ] Browser-check accessibility, photo contrast, image failure fallback, mobile layouts and the save/reload journey.

## W2 — Business-specific experience

- [x] Presentation keys and tenant business-line module filtering.
- [x] Retail sales terminology in orders list and navigation.
- [x] Supermarket/retail empty checkout lanes without guest, check or table prompts.
- [ ] Audit every critical order/detail/return, purchasing, report, inventory and employee workflow for irrelevant terminology.
- [ ] Browser-run each business profile: supermarket, independent retail, bar/lounge, restaurant, hotel, mixed business.
- [ ] Confirm filtered routes and APIs deny disabled business modules, not just hide nav links.

## W3/W4 — required certification

- [ ] PostgreSQL RLS against a non-owner app role and production-equivalent tenant context.
- [ ] Cross-domain custom apex/subdomain + platform subdomain DNS/HTTPS lifecycle.
- [ ] Real terminal pairing, PIN handover and print checks on desktop/tablet/mobile.
- [ ] Production deploy, smoke/rollback and final release sign-off.

**Current release status:** W1/W2 implementation underway; none of the remaining certification gates is implicitly satisfied by a commit.
