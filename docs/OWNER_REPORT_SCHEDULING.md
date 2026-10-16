# Scheduled owner sales reports

This opt-in feature extends the **existing** daily operations digest. The owner-configurable schedule is separate from the legacy global digest; do not enable both for the same business unless duplicate reports are intended.

## Set up

Open **Staff workspace → Settings → Owner email reports**. An active **owner or tenant administrator** signed in with an account password can configure the schedule. Shared PIN sessions are not authorized to change scheduled report recipients.

1. Choose a reporting scope. **One property** uses that property's operating-date window for sales and the property's configured timezone for delivery. **All business sections** reports UTC calendar periods, even though delivery follows the business timezone.
2. Choose **daily** (previous date), **weekly** (previous seven dates) or **monthly** (previous calendar month). Choose a local send hour (0–23). Weekly uses 0=Monday through 6=Sunday. Monthly may use dates 1–28 to avoid missing days in February.
3. Select one or more **currently active owner/admin accounts** as recipients. A normal cashier/server is never eligible. An inactive membership is excluded at delivery time.
4. Review example PDF/CSV downloads. These are read-only previews for the most recently completed day and never send emails or create financial entries.
5. Enable automatic email delivery and save. Reports are disabled by default for every tenant. Your mail provider and worker/scheduler must actually be configured; saving alone is not proof of delivery.

## Implementation

- `OwnerReportSchedule` is one configurable schedule per tenant. `OwnerReportDelivery` stores one unique entry per schedule/period and a **Sending**, **Sent** or **Failed** state, attempts and truncated error. Both include the tenant and PostgreSQL RLS.
- Celery beat runs `apps.api.tasks.dispatch_scheduled_owner_reports` hourly at minute 15. It checks each enabled business in the correct timezone and calls the existing scoped POS sales-summary calculation. Only active, permitted owner/admin recipients are used.
- The report email uses hidden recipients (BCC), with the current workspace's **PDF overview** and **CSV detail**. The PDF does not list guest or card data. The CSV formats use spreadsheet-formula escaping for item, location and free-text fields.
- A transient failure can be retried after 45 minutes, with a maximum of three attempts per period. A row in **Sending** is not automatically resent because SMTP may have accepted it before a crash. A production operator must review these cases against the mail provider before manual retries.
- Workers set and restore each tenant's PostgreSQL `app.tenant_id` context so per-tenant RLS applies in non-HTTP tasks, without keeping a database transaction open while sending an email.
- Normal outgoing email isn't enabled by this migration. No outbound network call is made until an authorized owner opts in, Celery beat invokes the task, and the email backend is configured.

## Deployment prerequisites and limitations

- Install the updated `backend/requirements.txt` including ReportLab. Use the repository's *actual* deploy configuration and service names; this note does not invent worker names.
- Apply the new tenant migrations and verify the PostgreSQL tenant RLS policy before enabling schedules.
- Confirm the project's Celery broker, beat and worker health, outbound SMTP credentials, FROM domain, recipient delivery, and email policy. Example owner PDF/CSV previews alone do not certify the mail system.
- Check recurring times around timezone and daylight-saving transitions on a staging database. DST-skipped local hours are handled by an hourly due check, but there is currently no automatic catch-up of days missed during a long outage.
- Revenue summaries are based on recorded POS payments/refunds. They do **not** provide bank reconciliation, gross margin, occupancy, supplier liabilities, inventory valuation or fiscal confirmation. Treat them as an operations digest rather than a complete accounting statement.
- Failure history is retained for the business owner. There is no claim of exactly-once email receipt: email transport cannot provide exactly-once guarantees without cooperation from the mail provider.
- PDF readability and delivery must be evaluated in the later verification pass against actual tenant names, languages, browsers and email clients.

## Design references

- Shopify POS opening checklist: https://help.shopify.com/en/manual/intro-to-shopify/shopify-pos-launch-checklist
- Django email reference: https://docs.djangoproject.com/en/5.2/topics/email/
- Celery periodic tasks: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
