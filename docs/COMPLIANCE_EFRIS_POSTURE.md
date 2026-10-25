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
- Evidence export is available from the staff EFRIS settings page as a tenant-scoped CSV containing submission id, canonical payload SHA-256, provider reference, attempts and hashed error evidence. Raw payloads, integration secrets and provider response bodies are not exported; provider response bodies are not currently retained.
- Add provider-certified response/error taxonomy and any required redacted response-evidence fields once URA/integrator contracts define stable codes and retention requirements.
- Explicit distinction between **EFD-mandatory** flows and **API-only** flows per tenant category.


## 2026-10-16 reliability safeguard (pending live certification)

- Automatic submission attempts are capped at **three**. Exhausted rows remain visible with their error and require operator assessment; they are not silently discarded or re-sent by the scheduler.
- If the adapter raises an unexpected exception (including a transport timeout where the provider may already have accepted the document), the row is **quarantined** after one attempted request with the message “Provider outcome unknown”. The automatic queue will not repeat the request.
- These safeguards are defensive engineering controls, **not** proof that the current generic adapter implements URA's certified transaction envelope. Prior to enabling real EFRIS submissions, reconcile any ambiguous outcome using the provider's fiscal reference/status lookup and URA-approved integration protocol. Do not manually re-enqueue until the outcome is known.
- URA's public handbook distinguishes e-invoices, e-receipts, credit notes and debit notes with fiscal identifiers and verification features. The current cashbook-linked integration shell does **not** establish that those document requirements, tax classifications or synchronous obligations are satisfied; provider sandbox evidence is required.
