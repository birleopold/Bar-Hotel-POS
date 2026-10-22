# Fizo Hotel — Individual Page Acceptance Register

Checked against tracked repository templates on 2026-10-22. Every one of the 13 hotel templates is listed below. The 12 screen templates and one shared subnavigation template are independently tracked.

**No page is VERIFIED** until Django rendering, actual browser review, interactive forms, permission checks, mobile/tablet and live deployment have been demonstrated. Source edits are not evidence of acceptance.

| # | Template (relative to `backend/apps/staff/templates/staff/lodging/`) | Owner/business category | Source status | Browser + functional acceptance |
|---:|---|---|---|---|
| 1 | `availability.html` | Hotel / room availability | New Fizo template/CSS committed | PENDING |
| 2 | `folios_list.html` | Hotel / guest accounts | Fizo screen layout committed; still untested | PENDING |
| 3 | `folio_detail.html` | Hotel / guest folio, payment | Fizo screen layout committed; still untested | PENDING |
| 4 | `housekeeping.html` | Hotel / housekeeping queues and status changes | Fizo shell/cards migrated; all forms retained | PENDING |
| 5 | `includes/subnav.html` | Hotel / shared property navigation | Fizo shared tabs committed; role conditions retained, still untested | PENDING |
| 6 | `maintenance.html` | Hotel / maintenance work orders | Fizo shell/cards migrated; management forms retained | PENDING |
| 7 | `night_audit.html` | Hotel / audit and business close | Fizo audit layout committed; financial close rules retained, still untested | PENDING |
| 8 | `reservation_detail.html` | Hotel / check-in, check-out, room assignment, folio | New Fizo presentation committed | PENDING |
| 9 | `reservation_form.html` | Hotel / create reservation | New Fizo presentation committed | PENDING |
| 10 | `reservations_list.html` | Hotel / front desk register | New Fizo presentation committed | PENDING |
| 11 | `room_types_list.html` | Hotel / room types and rate windows | New Fizo presentation committed | PENDING |
| 12 | `rooms_list.html` | Hotel / room directory | New Fizo presentation committed | PENDING |
| 13 | `tape_chart.html` | Hotel / occupancy timeline | Fizo screen layout committed; still untested | PENDING |

## Scope not contained in those 13 files

The hotel also uses common staff templates (`staff/base.html`, messages, form errors, shared search) and admin/organization templates for setup. Their appearance affects hotel staff, so they must be included in the shared-design acceptance register. `views_lodging.py`, forms, models, and lodging API endpoints are operational dependencies, not extra standalone hotel HTML templates.

## Acceptance evidence per page

1. Resolve real route and view, including outlet/site selection and role-based redirects.
2. Render with a real authenticated test tenant and representative data, plus empty/error states.
3. Exercise actual permitted and denied POST paths, including CSRF protection and tenant isolation.
4. Inspect desktop, tablet and phone browser screens against the four supplied Fizo reference images.
5. Confirm new stylesheet was collected and served, and no retired hospitality layout is loaded.
6. Record reproducible test result, deployed SHA, and screenshot; only then mark VERIFIED.

**All 13 hotel templates now have Fizo-source UI changes or shared navigation changes committed. None is marked VERIFIED until full Django tests, business workflow checks and authenticated browser comparison pass.** No false completion credit for merely switching stylesheets.


### 2026-10-22 continuation

Migrated remaining five templates: `folios_list.html`, `folio_detail.html`, `tape_chart.html`, `night_audit.html`, and `includes/subnav.html`. Preserved payment and close controls and added contract tests. **Browser-rendered fidelity to the supplied references and live functionality remain unverified.**
