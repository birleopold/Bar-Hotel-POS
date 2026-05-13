# EFRIS compliance posture (Uganda)

This document describes how the **optional** EFRIS integration in this codebase relates to Uganda Revenue Authority (URA) expectations, and what is **not** claimed without external validation.

Official references (verify current requirements before go-live):

- [URA EFRIS handbook](https://ura.go.ug/en/efris-handbook/)
- [URA Electronic Fiscal Device (EFD) information](https://ura.go.ug/en/efris/efd-issues/)

## Product behaviour

- **Global kill switch:** `EFRIS_INTEGRATION_ENABLED` in Django settings. When off, no queue rows are created regardless of tenant preferences.
- **Tenant toggle:** `TenantSettings.efris_enabled`. Most hotels can leave this off until they choose to adopt EFRIS-style submission.
- **Outbox:** `EfrisSubmission` rows link one-to-one to a `CashbookEntry` created through operational posting (e.g. POS-linked income). Processing runs on a Celery beat schedule with exponential backoff on failure.
- **Staff configuration:** `/staff/settings/integrations/efris/` stores non-secret preferences and masked secrets on the `ura_efris` integration link; health check calls the adapter.
- **Queue visibility:** The same page lists recent submissions (status, attempts, provider reference, **last error** text).

## What operators should know

- **`last_error`** is a short human-readable message from the HTTP adapter (e.g. HTTP/body parse failures). It is **not** a stable URA error-code taxonomy; use it for support, not automated branching.
- **Production readiness** may require URA-approved devices or vendor certification, specific payload fields, and environment-specific keys. Treat the shipped adapter as an **integration shell** until validated against your URA test environment or integrator.

## Roadmap (compliance hardening)

- Map responses to a documented error taxonomy where URA publishes stable codes.
- Evidence export (submission id, payload hash, response body redacted) for audits.
- Explicit distinction between **EFD-mandatory** flows and **API-only** flows per tenant category.
