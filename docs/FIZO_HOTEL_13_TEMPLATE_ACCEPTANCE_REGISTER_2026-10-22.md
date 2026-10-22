# Fizo Hotel — Individual Page Acceptance Register

Checked against tracked repository templates on 2026-10-22. Every one of the 13 hotel templates is listed below. The 12 screen templates and one shared subnavigation template are independently tracked.

**No page is VERIFIED** until Django rendering, actual browser review, interactive forms, permission checks, mobile/tablet and live deployment have been demonstrated. Source edits are not evidence of acceptance.

| # | Template (relative to `backend/apps/staff/templates/staff/lodging/`) | Owner/business category | Source status | Browser + functional acceptance |
|---:|---|---|---|---|
| 1 | `availability.html` | Hotel / room availability | New Fizo template/CSS committed | PENDING |
| 2 | `folios_list.html` | Hotel / guest accounts | Legacy UI remains | PENDING |
| 3 | `folio_detail.html` | Hotel / guest folio, payment | Legacy UI remains | PENDING |
| 4 | `housekeeping.html` | Hotel / housekeeping queues and status changes | Fizo shell/cards migrated; all forms retained | PENDING |
| 5 | `includes/subnav.html` | Hotel / shared property navigation | Shared legacy markup; requires individual redesign | PENDING |
| 6 | `maintenance.html` | Hotel / maintenance work orders | Fizo shell/cards migrated; management forms retained | PENDING |
| 7 | `night_audit.html` | Hotel / audit and business close | Legacy UI remains; safety-sensitive | PENDING |
| 8 | `reservation_detail.html` | Hotel / check-in, check-out, room assignment, folio | New Fizo presentation committed | PENDING |
| 9 | `reservation_form.html` | Hotel / create reservation | New Fizo presentation committed | PENDING |
| 10 | `reservations_list.html` | Hotel / front desk register | New Fizo presentation committed | PENDING |
| 11 | `room_types_list.html` | Hotel / room types and rate windows | New Fizo presentation committed | PENDING |
| 12 | `rooms_list.html` | Hotel / room directory | New Fizo presentation committed | PENDING |
| 13 | `tape_chart.html` | Hotel / occupancy timeline | Legacy UI remains | PENDING |

## Scope not contained in those 13 files

The hotel also uses common staff templates (`staff/base.html`, messages, form errors, shared search) and admin/organization templates for setup. Their appearance affects hotel staff, so they must be included in the shared-design acceptance register. `views_lodging.py`, forms, models, and lodging API endpoints are operational dependencies, not extra standalone hotel HTML templates.

## Acceptance evidence per page

1. Resolve real route and view, including outlet/site selection and role-based redirects.
2. Render with a real authenticated test tenant and representative data, plus empty/error states.
3. Exercise actual permitted and denied POST paths, including CSRF protection and tenant isolation.
4. Inspect desktop, tablet and phone browser screens against the four supplied Fizo reference images.
5. Confirm new stylesheet was collected and served, and no retired hospitality layout is loaded.
6. Record reproducible test result, deployed SHA, and screenshot; only then mark VERIFIED.

**Next outstanding hotel pages in order:** shared subnav, folio register/detail, occupancy tape, night audit. No false completion credit for merely switching stylesheets.
